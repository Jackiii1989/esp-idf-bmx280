---
name: code-review
description: Review C/C++ ESP-IDF code on ESP32-S3 for memory safety, FreeRTOS correctness, ISR safety, security vulnerabilities, performance, and ESP-IDF style conventions. Use when the user asks to review, audit, or check embedded C/C++ code. Invoke with /code-review [optional-path-or-file].
argument-hint: "[optional-file-or-directory]"
allowed-tools: Read, Glob, Grep, Bash
model: sonnet
context: fork
agent: Explore
effort: high
---

# ESP32-S3 Embedded Code Review

You are an expert embedded systems reviewer specializing in ESP-IDF C/C++ on ESP32-S3. Read the source files systematically, apply the full checklist below, and report findings grouped by severity with file names, line numbers, specific fixes, and — crucially — **why the pattern is problematic**. Explaining the design reasoning builds better instincts, not just a one-time fix.

Reference material in this skill folder:
- [memory-safety.md](memory-safety.md) — dangerous functions, pointer management, heap patterns, stack limits
- [freertos-patterns.md](freertos-patterns.md) — task creation, priority assignment, synchronization, ISR patterns
- [esp-idf-style.md](esp-idf-style.md) — naming conventions, include order, brace style, error handling
- [common-bugs.md](common-bugs.md) — integer overflow, sign conversion, concurrency bugs, security vulnerabilities

## Detect mode from argument

- **No argument** → full project review: find all `.c`, `.h`, `.cpp` files under `main/` and `components/`; include `CMakeLists.txt` files for build config issues
- **Single file path** → focused review on that file only; omit file path from findings (line numbers are enough)
- **Directory path** → review all C/C++ source files under that directory

---

## Review Checklist

### 1. Memory Safety

- **Dangerous string functions** — `strcpy`, `strcat`, `gets`, `sprintf`, `scanf("%s")` have no bounds checking and are the most common source of exploitable overflows on embedded targets. Any occurrence is a finding. Fix: `strncpy(dst, src, sizeof(dst) - 1)` + explicit null terminator, or `snprintf(buf, sizeof(buf), ...)`.
  > Why: On a bare-metal ESP32-S3 there is no OS memory protection — a stack overflow can overwrite the return address and redirect execution. In IoT devices this is especially dangerous because the device may be network-accessible.

- **NULL check after malloc/calloc/realloc** — every heap allocation must be checked before use. Return `ESP_ERR_NO_MEM` and log via `ESP_LOGE` on failure.
  > Why: The ESP32-S3 has ~512 KB SRAM split between tasks, drivers, and heap. Heap exhaustion is a runtime condition, not a programming bug — code must handle it gracefully, not crash.

- **realloc pattern** — `ptr = realloc(ptr, new_size)` leaks the original block when realloc fails (returns NULL). Always use a temp: `tmp = realloc(ptr, size); if (!tmp) { free(ptr); return; } ptr = tmp;`
  > Why: realloc on failure returns NULL but does not free the original pointer. Overwriting the only reference with NULL leaves the original block permanently leaked with no way to recover it.

- **Integer overflow in size calculations** — `count * sizeof(T)` can silently wrap on 32-bit arithmetic when `count` comes from external input. Check: `if (count > SIZE_MAX / sizeof(T)) { return ESP_ERR_INVALID_ARG; }` before multiplying.
  > Why: A wrapped size allocates a tiny buffer; subsequent writes cause heap corruption that manifests far from the allocation site, making it extremely difficult to diagnose.

- **Large local variables** — local arrays > ~256 bytes are a stack-overflow risk. ESP32-S3 task stacks are typically 2–4 KB; 10 KB buffers on the stack will silently overflow. Move to heap (malloc) or static storage.
  > Why: FreeRTOS task stacks are fixed at creation. Overflow writes into adjacent tasks' stacks or guard bytes, causing unpredictable corruption that is hard to reproduce.

- **Pointer to stack variable returned from function** — returning `&local_var` is undefined behaviour; the memory is freed when the function returns. Fix: return by value, use an out-parameter, or allocate on heap.
  > Why: The compiler may reuse the stack slot for a different variable in the caller, turning this into a silent data corruption rather than an immediate crash.

- **Pointer modified before free** — `ptr++; free(ptr);` passes the wrong address to the allocator, corrupting the heap. Use a separate iterator variable.
  > Why: The heap allocator stores metadata before the allocation boundary. Passing a misaligned pointer corrupts that metadata, causing a crash the next time any allocation or free is attempted.

- **Memory leak on early return** — functions that allocate and then `return` in an error branch without freeing. The `goto cleanup` pattern is idiomatic ESP-IDF for this.
  > Why: Leaks accumulate on long-running embedded devices. A device that runs for days without a reset will eventually exhaust the heap and enter an unrecoverable failure mode.

- **Use-after-free** — accessing a pointer after `free()`. Assign `ptr = NULL` immediately after freeing to catch accidental reuse at the next dereference.
  > Why: The freed memory may be reallocated to another subsystem. Writing through the stale pointer silently corrupts unrelated data.

- **Uninitialized variables** — local variables read before assignment produce undefined behaviour. Always initialize to a safe default at declaration or check the return value of the function that sets them.
  > Why: Compilers may keep the variable in a register that held garbage from a previous call. The value is non-deterministic across builds and optimization levels, making bugs impossible to reproduce consistently.

- **Off-by-one in array indexing** — `i <= sizeof(buf)` or `strncpy(buf, src, sizeof(buf))` (no room for `\0`). Loop bounds must use strict `<`; string copies must reserve one byte.
  > Why: Writing one byte past the end of a buffer corrupts the next variable in memory. On a stack frame this may overwrite a return address or saved register.

---

### 2. FreeRTOS & Real-Time Correctness

- **Task created without return-value check** — `xTaskCreate`/`xTaskCreatePinnedToCore` returns `pdPASS` on success. An unchecked failure leaves the system silently missing a task.
  > Why: If heap is exhausted at startup, task creation silently fails. The missing task causes downstream failures with no log evidence of the root cause.

- **Missing `vTaskDelete(NULL)` at task exit** — a task function that returns without calling `vTaskDelete(NULL)` causes a crash. Every task loop must be infinite or end with `vTaskDelete(NULL)`.
  > Why: FreeRTOS does not allow task functions to return normally — the stack frame becomes invalid but the TCB still exists, causing a hard fault on the next context switch.

- **Blocking in high-priority task without yielding** — a `while(1)` loop in a high-priority task with no `vTaskDelay`, `xQueueReceive`, or other blocking call starves all lower-priority tasks including the WiFi stack and idle task.
  > Why: The FreeRTOS scheduler is cooperative at the same priority level. A CPU-bound high-priority task runs forever, the idle task never runs, and the watchdog fires after ~5 seconds.

- **Stack size too small** — task created with fewer words than its locals + call depth require. Use `uxTaskGetStackHighWaterMark(NULL)` during development to validate. Flag any task using ≤ 512 words with non-trivial logic.
  > Why: Stack overflow silently corrupts the memory below the stack. The resulting crash occurs in an unrelated location, often with a `LoadProhibited` or `StoreProhibited` core dump.

- **Priority inversion** — a high-priority task blocked on a mutex held by a low-priority task while a medium-priority task runs freely. Use `xSemaphoreCreateMutex()` (which supports priority inheritance) instead of a binary semaphore for resource protection.
  > Why: Without priority inheritance the high-priority task can be blocked indefinitely by a medium-priority task that was never designed to block it — violating real-time guarantees.

- **Deadlock from circular mutex acquisition** — Task A holds mutex 1 and waits for mutex 2; Task B holds mutex 2 and waits for mutex 1. Fix: always acquire mutexes in a globally consistent order.
  > Why: Both tasks block permanently. The system continues running (watchdog may not trigger) but the affected subsystem is frozen with no log evidence unless a timeout is used.

- **Wrong synchronization primitive for ISR** — using `xSemaphoreTake`/`xSemaphoreGive` (not `FromISR`) inside an ISR. ISR versions return a `pxHigherPriorityTaskWoken` that must be passed to `portYIELD_FROM_ISR`.
  > Why: Non-ISR FreeRTOS functions may block, allocate, or disable interrupts in ways that are illegal inside an ISR. The symptom is a random hard fault that is not reproducible reliably.

- **Task handle not stored when control is needed later** — passing `NULL` for the task handle parameter means the task cannot be suspended, resumed, or deleted later.
  > Why: In systems that need graceful shutdown or dynamic reconfiguration, lost handles make clean teardown impossible and force a full reboot instead.

- **`portMAX_DELAY` on non-debug paths without timeout handling** — blocking indefinitely in production code hides liveness bugs. Use a finite timeout and handle the timeout case.
  > Why: `portMAX_DELAY` converts a transient bug (producer died) into a permanent freeze. A finite timeout surfaces the problem in logs and allows recovery.

---

### 3. ISR Safety

- **IRAM_ATTR missing on ISR handlers** — functions called from ISRs (including callbacks registered with driver APIs) must be in IRAM, or they will crash when the flash cache is disabled during a flash write.
  > Why: The ESP32-S3 XTS-AES flash encryption and OTA updates disable the flash cache briefly. If the ISR handler is in flash (the default), a cache miss during that window causes an `IRAM_ATTR` violation and hard fault.

- **Non-volatile shared variable between ISR and task** — variables written in ISR context and read in task context must be `volatile`. Without it the compiler is free to cache the value in a register and never re-read from memory.
  > Why: `-O2`/`-Os` (ESP-IDF defaults) optimizes repeated reads of the same variable into a single register load. The task loop sees the stale register value and never observes the ISR's update.

- **Blocking call inside ISR** — `vTaskDelay`, `xQueueReceive`, `xSemaphoreTake`, `ESP_LOGI`, `malloc`, `printf` are all illegal inside an ISR. Flag any occurrence.
  > Why: FreeRTOS blocking functions call the scheduler, which is not re-entrant from ISR context. The result is a corrupted scheduler state and eventual hard fault.

- **`portYIELD_FROM_ISR` not called when task woken** — ISR gives semaphore/queue via `*FromISR` variant but ignores the `xHigherPriorityTaskWoken` output. The woken task does not run until the next scheduled tick, introducing up to 1 tick of latency.
  > Why: Without the yield, a real-time task waiting for the ISR signal runs up to `configTICK_RATE_HZ` ms late — which can violate timing constraints and cause missed samples.

- **Long ISR execution** — ISR body contains loops, string operations, or multiple driver calls. ISRs must complete in microseconds. Move work to a task signaled by the ISR.
  > Why: Long ISRs block all other interrupts at the same or lower priority. On a dual-core ESP32-S3, an ISR running on PRO_CPU blocks PRO_CPU interrupts for its duration, which can cause WiFi/BT stack glitches.

- **Critical section too wide** — `portENTER_CRITICAL` / `portEXIT_CRITICAL` wrapping large code blocks including I/O. Critical sections disable all interrupts on the calling core; keep them to the minimum required to read/write the shared variable atomically.
  > Why: Every microsecond in a critical section is a microsecond where interrupts cannot be serviced — timer interrupts, WiFi ticks, and UART receive all queue up.

---

### 4. Security

- **Format string vulnerability** — `printf(user_input)` / `ESP_LOGI(TAG, user_input)` passes user-controlled data as a format string. Always pass user input as a `%s` argument.
  > Why: `%n` format specifier writes to memory; `%x` sequences read the stack. On a network-connected IoT device this is a remote memory read/write primitive.

- **Path traversal** — filenames from network or user input concatenated into SPIFFS/LittleFS paths without stripping `..` or `/`. Check with `strchr(filename, '/') || strstr(filename, "..")`.
  > Why: An attacker can read `/etc/wifi_config` or overwrite firmware files by injecting `../` into a filename parameter.

- **Unchecked external input used as array index or size** — network packet fields, MQTT payloads, or BLE characteristic values used directly as array indices or malloc sizes without range validation.
  > Why: Network-connected embedded devices receive attacker-controlled data. Every external field that influences memory layout must be bounds-checked before use.

- **Hardcoded credentials** — WiFi passwords, API keys, or TLS pre-shared keys in source code or `sdkconfig.defaults`. Flag any string literal that looks like a credential.
  > Why: Source code ends up in version control and firmware binaries. Credentials baked into firmware can be extracted by anyone with the binary via `strings firmware.bin`.

- **`ESP_ERROR_CHECK` on recoverable errors** — using `ESP_ERROR_CHECK` (which calls `abort()`) on operations that can legitimately fail at runtime (network errors, sensor timeouts, user input). Reserve it for programming-error guards in init paths.
  > Why: `abort()` reboots the device, causing a denial-of-service. A network error should be retried or logged, not treated as fatal.

- **TLS certificate verification disabled** — `esp_tls_cfg_t` with `skip_common_name = true` or `crt_bundle_attach = NULL` when connecting to external services.
  > Why: Disabling certificate verification makes HTTPS connections as insecure as HTTP — a network attacker can intercept and modify the traffic without the device detecting it.

---

### 5. Performance & Resource Efficiency

- **Busy-wait loop** — `while (!flag) {}` or `while (!flag) { /* nothing */ }` without a delay. On a preemptive RTOS this burns 100% of the core and may trigger the task watchdog.
  > Why: The busy-waiting task never yields. Lower-priority tasks (including idle, WiFi, BT) cannot run. After ~5 seconds the task watchdog fires and reboots the device.

- **`vTaskDelay(0)` used as yield** — `vTaskDelay(0)` on some FreeRTOS configurations does not yield; use `taskYIELD()` explicitly if a yield without delay is intended.
  > Why: The behaviour of delay(0) is implementation-defined. `taskYIELD()` has unambiguous semantics.

- **Logging inside tight loops or high-frequency callbacks** — `ESP_LOGI` / `printf` inside timer callbacks, ADC ISRs, or loops that run faster than ~100 Hz. `ESP_LOGI` is synchronous and can block for milliseconds.
  > Why: Each UART log write holds the log mutex. At high frequency this turns a sensor loop into a logging bottleneck, causes missed samples, and can trigger the watchdog.

- **Dynamic allocation in real-time paths** — `malloc`/`free` inside a control loop or periodic timer callback. Heap allocation is non-deterministic (can block, fragment, and fail).
  > Why: Real-time control requires deterministic timing. A single failed malloc in a 10 ms control loop can cause a missed deadline and unstable control output.

- **Unnecessary core pinning** — all tasks pinned to core 0 (PRO_CPU) when some could run on core 1 (APP_CPU). WiFi/BT stack prefers core 0; computation-heavy tasks should prefer core 1.
  > Why: Concentrating all application tasks on the same core as the WiFi stack causes priority contention and increases WiFi latency.

- **Large stack reservation without evidence** — task created with 8192+ words with no comment explaining why. Over-allocation wastes SRAM that is a shared, limited resource.
  > Why: The ESP32-S3 has ~512 KB SRAM. Wasting 32 KB on an oversized task stack may prevent another task from being created or cause OOM failures in the driver layer.

- **Polling `esp_timer` or hardware flag without blocking primitive** — checking a flag with a tight `vTaskDelay(1)` loop instead of using a semaphore/queue to wake on the event.
  > Why: A 1 ms polling loop invokes the scheduler 1000 times/second. Using a semaphore or task notification is zero-overhead when there is no event and wakes the task immediately when there is.

---

### 6. ESP-IDF Style & Conventions

- **Include order violated** — includes must follow: C stdlib → POSIX → IDF common → FreeRTOS → driver/peripheral → project components → private headers. Mixed order causes subtle dependency issues and makes include auditing harder.
  > Why: Out-of-order includes can mask missing includes in other files (a header accidentally included transitively). Consistent order makes each file self-contained and easier to verify.

- **Missing `#pragma once`** — header files without an include guard. All headers must have `#pragma once` as the first non-comment line.
  > Why: Without a guard, including the same header twice (common via transitive includes) causes duplicate symbol errors or, worse, duplicate `static` variable definitions that silently disagree.

- **Missing `extern "C"` guard in headers** — headers included in both C and C++ translation units need `#ifdef __cplusplus extern "C" { #endif` to prevent C++ name mangling of C function declarations.
  > Why: Without the guard, a C++ file including a C header generates mangled symbol names. The linker cannot match them to the C objects and produces "undefined reference" errors.

- **camelCase or PascalCase function names** — ESP-IDF convention is `snake_case` for all functions and variables. camelCase is a sign of a port from Arduino or other frameworks.
  > Why: Inconsistent naming makes code harder to search and grep. ESP-IDF APIs are all snake_case; mixing styles requires the reader to remember which convention applies where.

- **Static variables not prefixed with `s_`** — static file-scope variables should be named `s_variable_name`. This signals to the reader that the variable has file scope and is not a local.
  > Why: Without the prefix, a reader has to scroll to the declaration to determine variable scope. The `s_` prefix makes scope visible at every use site.

- **Public API functions not prefixed with component name** — public functions in a component named `my_sensor` should be `my_sensor_init()`, `my_sensor_read()`, etc.
  > Why: Without a prefix, public symbols from different components collide in the global namespace. ESP-IDF's linker will accept the collision silently, using whichever symbol comes first.

- **Brace style incorrect** — function definition braces must be on a new line; control-flow braces (`if`, `for`, `while`) must be on the same line as the keyword.
  > Why: The Espressif style guide is explicit about this. Inconsistent brace style in a shared codebase increases review noise and makes `git diff` harder to read.

- **4-space indentation not used** — tabs or 2-space indentation. ESP-IDF uses 4 spaces.
  > Why: Mixed indentation causes misalignment when editors have different tab-width settings, and confuses static analysis tools that count indentation levels.

- **`esp_err_t` return code not checked** — calling an ESP-IDF function that returns `esp_err_t` and discarding the result without `if (err != ESP_OK)` or `ESP_ERROR_CHECK`.
  > Why: Silent failure of an init call (e.g., `i2c_master_bus_create`) means subsequent driver calls use an invalid handle, producing confusing `ESP_ERR_INVALID_STATE` errors far from the root cause.

- **Magic numbers** — raw integer literals in logic that should be named constants (`#define` or `static const`). Applies to pin numbers, timeouts, queue depths, buffer sizes.
  > Why: Magic numbers cannot be searched and are not self-documenting. When the same value appears in three places, a future change updates two of them and misses the third.

- **`assert` with side effects** — `assert(some_function())` — if `NDEBUG` is defined (release build), the function call is omitted entirely.
  > Why: Code that works in debug and silently breaks in release is the hardest class of bug to diagnose. Store the result in a variable before asserting.

- **Unused parameter not suppressed** — function parameters that are not used generate `-Wunused-parameter` warnings. Suppress with `(void)param;` or `__attribute__((unused))`.
  > Why: Unaddressed warnings train developers to ignore the warning output, causing real warnings (sign conversion, unused results) to be missed.

---

### 7. Architecture & Design Quality

- **Component structure not used** — all code in `main/` rather than split into `components/` for reusable subsystems (sensors, protocol handlers, hardware drivers).
  > Why: Code in `main/` cannot be reused across projects or tested in isolation. Espressif's component model exists precisely to enforce single-responsibility and testability boundaries.

- **Driver logic mixed with application logic** — hardware read/write calls (`i2c_master_transmit`, `gpio_set_level`) in the same function as business logic (state machines, protocol parsing).
  > Why: Mixed concerns make unit testing impossible and hardware swaps expensive. A HAL boundary (thin driver layer + abstract interface) decouples them.

- **Global mutable state shared between components** — `extern` variables used to share state between `.c` files in different components.
  > Why: Global mutable state creates invisible coupling. Any file can modify the state at any time, making data-flow analysis and debugging difficult. Pass state through function parameters or a message queue.

- **ISR communicates via global flag, not queue/semaphore** — `volatile bool s_flag = false;` set in ISR, polled in task. This pattern only works for the simplest binary events and loses events if the task does not poll before the next ISR fires.
  > Why: A single `volatile` bool cannot queue multiple events. A semaphore or queue buffers pending events and provides proper task-wake semantics.
  > Exception: The pattern `volatile bool s_ready; volatile float s_value;` (set atomically in a timer callback, read in the main loop after checking the flag) is acceptable for single-producer, single-consumer float data where losing an update is acceptable (e.g., RPM smoothing over 800 ms). See the `rpm_unit` component in `esp-idf-bmx280` for a real example.

- **`app_main` too large** — `app_main` contains more than ~30 lines of initialization, task creation, and event loop logic. It should delegate to `component_init()` functions.
  > Why: A large `app_main` is a sign of missing component boundaries. Initialization logic that lives in `app_main` cannot be tested independently or reused.

- **No error handling strategy** — init code uses `ESP_ERROR_CHECK` throughout (abort on any error) with no distinction between unrecoverable programming errors and recoverable runtime conditions (sensor not found, network timeout).
  > Why: A well-designed embedded system distinguishes "this should never happen" (abort is correct) from "this might happen at runtime" (log, retry, or degrade gracefully). An `abort()` from a missing optional sensor is user-hostile.

- **`CMakeLists.txt` missing component dependencies** — `target_link_libraries` in a component's `CMakeLists.txt` does not list all components it actually uses (relies on transitive deps).
  > Why: Transitive deps are an implementation detail of the dependency. When that intermediate component changes its own deps, the build silently breaks. Explicit deps are self-documenting and robust.

---

## Output Format

```
## Embedded Code Review: <path or "Full Project">

### 🔴 Critical (fix before ship)
- **[File:Line]** Description — _Why:_ explanation — Fix: concrete corrected code

### 🟠 High (fix soon)
- **[File:Line]** Description — _Why:_ explanation — Fix: corrected code or pattern

### 🟡 Medium (improve when touching)
- **[File:Line]** Description — _Why:_ explanation

### 🔵 Style / Convention
- **[File:Line]** Description

### 🏗️ Architecture Observations
- Structural observations that span multiple files

### ✅ Notable Good Patterns
- Patterns worth calling out as examples to follow elsewhere in the codebase
```

Severity guide:
- **Critical** — memory corruption, ISR safety violation, security vulnerability, code that will crash or corrupt data
- **High** — real-time correctness bug, resource leak, incorrect FreeRTOS usage, `esp_err_t` result silently ignored
- **Medium** — performance issue, best-practice violation, missing guard that could become a bug with future changes
- **Style** — naming, formatting, include order, comment quality
- **Architecture** — structural observations; never block-level bugs but still worth addressing for maintainability
