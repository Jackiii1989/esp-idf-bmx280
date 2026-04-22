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
- [memory-safety.md](memory-safety.md) — dangerous functions, pointer management, heap patterns, stack limits, PSRAM/DMA
- [freertos-patterns.md](freertos-patterns.md) — task creation, priority assignment, synchronization, ISR patterns
- [esp-idf-style.md](esp-idf-style.md) — naming conventions, include order, brace style, error handling
- [common-bugs.md](common-bugs.md) — integer overflow, sign conversion, concurrency bugs, security vulnerabilities
- [peripheral-drivers.md](peripheral-drivers.md) — PCNT, I2C Master, NVS, esp_timer patterns and known driver bugs
- [iram-flash-cache.md](iram-flash-cache.md) — IRAM safety, flash cache disable window, driver _ISR_IRAM_SAFE Kconfig options

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

- **`_ISR_IRAM_SAFE` Kconfig option missing for driver using ISR callbacks** — for PCNT, GPTimer, SPI Master, and GPIO, adding `IRAM_ATTR` to the user callback alone is insufficient; the driver's own interrupt dispatch code also lives in flash by default and must be moved to IRAM via the corresponding `CONFIG_<DRIVER>_ISR_IRAM_SAFE` Kconfig option. See [iram-flash-cache.md](iram-flash-cache.md) for the full table.
  > Why: When the flash cache is disabled (NVS commit, OTA write), the CPU executes the driver's ISR dispatch code from flash — causing an immediate cache-miss panic before the user callback is ever reached. `IRAM_ATTR` on the user callback does not protect the driver's dispatch path.

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

### 8. ESP32-S3 Hardware-Specific Pitfalls

- **PSRAM/DMA cache coherency violation** — allocating a buffer with `malloc()` (internal DRAM) and passing it to a DMA-capable driver is fine. But allocating from PSRAM (`MALLOC_CAP_SPIRAM`) and passing to DMA requires explicit cache synchronization: call `esp_cache_msync(buf, len, ESP_CACHE_MSYNC_FLAG_DIR_C2M)` after CPU writes (before DMA reads) and `ESP_CACHE_MSYNC_FLAG_DIR_M2C` after DMA writes (before CPU reads). Missing this causes the CPU to read stale cached data.
  > Why: On ESP32-S3, PSRAM is accessed via a cache. DMA bypasses the cache and writes directly to SPIRAM. Without `esp_cache_msync()`, the CPU reads old values from its cache rather than what DMA wrote.

- **DMA descriptors placed in PSRAM** — the DMA hardware (SPI, I2S, LCD, etc.) requires its descriptors (linked list nodes) to be in internal DRAM, not PSRAM. Allocate them with `heap_caps_malloc(size, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL)`.
  > Why: The DMA engine cannot address PSRAM for its control structures. Placing descriptors there causes silent transfer failures or hard faults during DMA operations.

- **Large static arrays consuming IRAM** — `static uint8_t large_buf[8192];` in a `.c` file goes into DRAM by default, but if it ends up in a section linked to IRAM (e.g., placed in IRAM_ATTR translation unit), it wastes the precious ~400 KB IRAM. Add `DRAM_ATTR` to force DRAM placement: `static DRAM_ATTR uint8_t large_buf[8192];`
  > Why: IRAM is a shared resource for ISR handlers and time-critical code. Wasting it on data arrays leaves less room for IRAM_ATTR functions and increases cache miss pressure.

- **DMA-capable PSRAM allocation** — when you need a large DMA buffer in PSRAM, use `esp_dma_malloc(size, ESP_DMA_MALLOC_FLAG_PSRAM, (void **)&buf, &actual_size)` (ESP-IDF >= 5.2). This is the recommended API and satisfies both cache-line and DMA alignment in one call. On older versions, `heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_DMA)` is still valid.
  > Why: Plain `heap_caps_malloc(size, MALLOC_CAP_SPIRAM)` may return an address that is not DMA-aligned, causing bus faults when the DMA hardware tries to access it. `esp_dma_malloc` encapsulates the correct alignment logic and is the Espressif-recommended path in ESP-IDF 5.x+ documentation.

- **Flash cache disabled window not covered by IRAM_ATTR** — during OTA writes, `nvs_commit()`, or flash encryption operations, the flash cache is briefly disabled. Any code not in IRAM that runs at this moment (timer callbacks, FreeRTOS hooks, driver callbacks) will crash with `Cache disabled but cached memory region accessed`.
  > Why: Unlike IRAM_ATTR on ISR handlers (which is well-known), callback functions registered with `esp_timer`, `pcnt_unit_register_event_callbacks`, and similar APIs are easy to forget. All such callbacks must also carry `IRAM_ATTR`.

- **`esp_cache_msync` called on non-cache-line-aligned buffer** — `esp_cache_msync()` requires both the buffer address and size to be aligned to the cache line size (64 bytes on ESP32-S3). A call on a buffer from plain `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` (not DMA-aligned) returns `ESP_ERR_INVALID_ARG` silently and performs no synchronization, leaving the CPU reading stale data. Always allocate PSRAM buffers used with `esp_cache_msync` via `esp_dma_malloc()` or `heap_caps_malloc(..., MALLOC_CAP_SPIRAM | MALLOC_CAP_DMA)`.
  > Why: Cache-line alignment is a hardware requirement of the cache coherency controller. An unaligned sync call fails silently — no error is logged, the CPU reads old cached values after DMA writes, and the corruption has no obvious cause.

- **All tasks pinned to core 0** — on dual-core ESP32-S3, pinning every application task to PRO_CPU (core 0) competes with the WiFi/BT stack which prefers core 0. Computation-heavy tasks should be pinned to APP_CPU (core 1) or left unpinned.
  > Why: WiFi runs at a high priority on core 0. Saturating core 0 with application tasks increases WiFi latency, causes Tx/Rx packet drops, and can trigger WiFi watchdog resets.

---

### 9. esp_timer Callback Pitfalls

- **Blocking inside an ESP_TIMER_TASK callback** — by default, `esp_timer` dispatches callbacks from a single high-priority `esp_timer` task. Blocking (`vTaskDelay`, `xSemaphoreTake`, `ESP_LOGI`, `malloc`) in a callback delays every subsequent pending callback because execution is serialized.
  > Why: The esp_timer task processes all TASK-dispatch timers sequentially. A 50 ms blocking call inside one callback pushes all other timers out by 50 ms, violating their periods.

- **`portYIELD_FROM_ISR` called from ESP_TIMER_ISR callback** — timers created with `ESP_TIMER_ISR` dispatch run inside the hardware timer ISR. Calling `portYIELD_FROM_ISR()` directly is illegal; use `esp_timer_isr_dispatch_need_yield()` instead, which schedules the yield after all ISR-dispatch callbacks complete.
  > Why: The ISR dispatch mode processes multiple timer callbacks in one ISR invocation. An intermediate `portYIELD_FROM_ISR()` would exit before remaining callbacks run, causing missed firings.

- **`esp_timer_start`/`esp_timer_stop` called from inside an ISR-dispatch callback** — modifying timer state from within an `ESP_TIMER_ISR` callback is illegal and undefined.
  > Why: The timer API acquires an internal spinlock. Calling it while already holding the same lock from ISR context causes a deadlock or assertion failure.

- **Timer callback doing real work instead of signaling** — if a timer callback does I2C reads, string formatting, or anything non-trivial, move the work to a task. Signal the task with `xTaskNotifyGiveFromISR` (for ISR dispatch) or a semaphore give (for TASK dispatch).
  > Why: Long callbacks block the esp_timer task (TASK mode) or extend the ISR window (ISR mode), both of which degrade system responsiveness and can trigger the interrupt watchdog.

- **esp_timer handle not deleted on cleanup path** — `esp_timer_delete()` must be called after `esp_timer_stop()` when tearing down a subsystem. Leaking the handle leaves the timer registered permanently.
  > Why: A stopped timer's handle still occupies memory in the timer list. Re-initializing the subsystem and creating a new timer without deleting the old one eventually exhausts the timer handle pool.

- **Periodic timer + light sleep firing burst** — when `CONFIG_PM_ENABLE` is set and the device enters light sleep, a periodic `esp_timer` continues to logically expire but its callbacks are deferred. On wakeup, all accumulated missed firings execute back-to-back. For timers that drive sampling loops, this burst causes spurious data points and can overflow the esp_timer task queue. Set `skip_unhandled_events = true` in `esp_timer_create_args_t` to coalesce all missed firings into a single post-wakeup callback.
  > Why: A 200 ms periodic timer that fires 5 times during a 1-second sleep will execute its callback 5 times in rapid succession on wakeup. Without `skip_unhandled_events`, the burst is indistinguishable from a real high-rate event, and the application's state machine or sensor loop may process stale back-dated data.

---

### 10. Peripheral Driver Pitfalls (PCNT, I2C Master, NVS)

#### PCNT (Pulse Counter)

- **PCNT watchpoint/event callback violating ISR rules** — callbacks registered via `pcnt_unit_register_event_callbacks()` are invoked from ISR context. They must not block, must not call non-ISR FreeRTOS APIs, and should use `xQueueSendFromISR` / `vTaskNotifyGiveFromISR` to defer work.
  > Why: Like any ISR, PCNT event callbacks run with the CPU's interrupt flag set. Calling `xQueueReceive` or `ESP_LOGI` from one causes a FreeRTOS assertion or corrupted scheduler state.

- **Glitch filter configured after unit enabled** — `pcnt_unit_set_glitch_filter()` must be called while the unit is in the `init` state (before `pcnt_unit_enable()`). Calling it afterward returns `ESP_ERR_INVALID_STATE` and the filter is not applied.
  > Why: The PCNT hardware latches the filter configuration at enable time. Post-enable changes are rejected to prevent mid-operation reconfiguration.

- **APB clock instability with glitch filter under power management** — if `CONFIG_PM_ENABLE` is set and the device can enter light sleep, the APB clock frequency may change, causing the glitch filter (which is APB-clock-based) to misinterpret valid pulses as noise. In ESP-IDF >= 5.3.2 (including v6.0), `pcnt_unit_enable()` unconditionally acquires the `ESP_PM_APB_FREQ_MAX` lock — the device cannot enter light sleep while any PCNT unit is enabled, with or without a glitch filter. In earlier versions (< 5.3.2) the lock was only acquired when a glitch filter was configured. Verify this side-effect is acceptable for your power budget; call `pcnt_unit_disable()` when the counter is not needed.
  > Why: The glitch filter's `max_glitch_ns` is converted to APB cycles at configuration time. If APB slows down, the cycle count stays the same but the effective glitch width changes, silently dropping legitimate pulses. The unconditional lock in 5.3.2+ is a correctness fix but prevents all light sleep while the PCNT unit is enabled.

- **PCNT counter not cleared before first read** — after `pcnt_unit_enable()` + `pcnt_unit_start()`, the hardware counter may contain a non-zero residual value. Call `pcnt_unit_clear_count()` before the first timed window to avoid an erroneous first RPM reading.
  > Why: The PCNT hardware preserves its count register across enable/disable cycles. A leftover count from a previous run or power-on state adds phantom pulses to the first measurement window.

#### I2C Master (driver/i2c_master.h)

- **Bus handle and device handle lifecycle mismatch** — `i2c_master_bus_handle_t` is created once per bus via `i2c_new_master_bus()`; `i2c_master_dev_handle_t` is created per device via `i2c_master_bus_add_device()`. Deleting the bus handle while device handles are still attached, or vice versa, is undefined.
  > Why: The bus handle owns the hardware resource. Deleting it invalidates all device handles that reference it, but the driver has no way to notify them — subsequent device operations crash.

- **Mixing old `driver/i2c.h` and new `driver/i2c_master.h` APIs** — the two drivers are mutually exclusive. Calling `i2c_driver_install()` and then `i2c_new_master_bus()` on the same port, or including both headers, causes undefined behaviour.
  > Why: The old and new drivers both try to configure the same I2C peripheral registers and interrupt vectors. Double-initialization corrupts the hardware state.

- **`i2c_master_transmit_receive()` returning ESP_OK on NACK** — a known ESP-IDF issue: if the device NAKs the address byte, some driver versions still return `ESP_OK`. Do not assume a successful return means the device acknowledged the transaction; validate data plausibility where possible.
  > Why: Silent NACK means the bus completed a transaction but the device never responded. Reading sensor values from a device that is not present returns garbage data that looks like valid readings.

- **Timeout not set for clock-stretching devices** — devices that do clock stretching (e.g., BME280 during measurements) may hold SCL low beyond the default timeout, causing `ESP_ERR_TIMEOUT`. Set `i2c_master_dev_config_t::scl_wait_us` to a value larger than the device's maximum stretch time.
  > Why: The default timeout is short (typically a few hundred µs). A sensor that stretches clock for 2–3 ms (e.g., during forced-mode measurement) will reliably time out and return an error even when the device is working correctly.

#### NVS (Non-Volatile Storage)

- **Missing `nvs_commit()` after write** — `nvs_set_*()` functions write to an in-memory cache; the data is not guaranteed to persist across a reboot until `nvs_commit()` is called.
  > Why: If the device reboots between `nvs_set_u32()` and `nvs_commit()`, the update is silently lost. For configuration values this means the device reverts to defaults unexpectedly.

- **Namespace or key longer than 15 characters** — NVS namespaces and keys are silently truncated to 15 characters. Two keys that share the first 15 characters collide.
  > Why: NVS stores keys as fixed-length 16-byte fields (15 chars + null). Truncation is not an error — it causes a silent collision where two different logical keys read and write the same physical entry.

- **Handle not closed after use** — `nvs_close()` must be called when the handle is no longer needed. Open handles consume NVS internal resources.
  > Why: NVS has a limited number of open handle slots. Leaking handles eventually causes `nvs_open()` to return `ESP_ERR_NVS_NOT_ENOUGH_SPACE` even when NVS flash is not full.

- **Not handling `ESP_ERR_NVS_NO_FREE_PAGES`** — on first boot or after a flash erase, `nvs_flash_init()` may return this error. The correct recovery is: `nvs_flash_erase(); nvs_flash_init();`
  > Why: NVS uses a wear-leveling scheme that can leave the partition in an unclean state after a power loss during write. Erasing and reinitializing recovers the partition at the cost of all stored values.

---

### 11. C++ Pitfalls (main.cpp / C++ translation units)

- **FreeRTOS primitives used in global constructors** — global C++ objects with constructors run before `app_main()` is called, and critically, before the FreeRTOS scheduler starts. Do not call `xTaskCreate`, `xTaskCreatePinnedToCore`, or any blocking FreeRTOS API in a global constructor. Queue and semaphore *creation* (`xQueueCreate`, `xSemaphoreCreateBinary`) allocates from the heap and may appear to succeed, but any API that requires the scheduler to be running is undefined behaviour.
  > Why: The FreeRTOS heap is initialized during secondary system init, which runs before constructors — so `xQueueCreate` may succeed in a constructor but `xTaskCreate` will not. The scheduler itself starts later when the main task is created. Per the ESP-IDF v6.0 Application Startup Flow docs, constructors always run before `vTaskStartScheduler()`. Defer all scheduler-dependent initialization to `app_main` or an `ESP_SYSTEM_INIT_FN`-annotated component init function.

- **Exceptions silently disabled** — ESP-IDF disables C++ exceptions by default (`CONFIG_COMPILER_CXX_EXCEPTIONS=n`). Any `throw` (including implicit ones from `std::bad_alloc`, `std::out_of_range`) calls `abort()` immediately. Code ported from desktop that relies on `try`/`catch` will crash the device instead of recovering.
  > Why: The toolchain replaces exception unwind machinery with `abort()` to save code size. A `std::vector::at()` out-of-range access — harmless with exceptions — reboots the ESP32.

- **`new` without `nothrow` in embedded context** — `new T()` throws `std::bad_alloc` on allocation failure when exceptions are enabled. With exceptions disabled, it calls `abort()`. Use `new (std::nothrow) T()` and check for `nullptr` to get the same safe pattern as `malloc`.
  > Why: On an ESP32 with limited heap, allocation failures are runtime conditions, not programming errors. Aborting on OOM is user-hostile; returning `nullptr` allows graceful degradation.

- **`std::string` / STL containers in high-frequency paths** — `std::string`, `std::vector`, etc. call `malloc`/`free` internally. Using them in a control loop, timer callback, or ISR-signaled task introduces non-deterministic allocation latency and fragmentation.
  > Why: Heap allocation is non-deterministic on embedded targets. A sensor loop that builds a `std::string` for each CSV line will eventually block on a slow `malloc` and miss a timing deadline.

- **Static local variable initialization race** — C++11 guarantees thread-safe initialization of static local variables via `__cxa_guard_acquire`. On multi-core ESP32-S3, this acquire may spin-wait. In ISR context it will deadlock if the guard is already locked by a preempted task.
  > Why: `__cxa_guard_acquire` uses a spinlock-style protocol. An ISR that triggers first-time initialization of a static local will spin forever if the initialization was already in progress on the other core.

- **`static` C++ objects with non-trivial destructors** — destructors of global/static C++ objects are registered with `atexit()`. On ESP32, `atexit` handlers do not run on `abort()` or power cycle — only on graceful `exit()`, which almost never happens. Relying on destructors for cleanup (releasing semaphores, flushing NVS) is unreliable.
  > Why: Embedded systems rarely call `exit()` cleanly. If the device is rebooted via `esp_restart()` or `abort()`, destructors never run, leaving hardware in an undefined state.

---

### 12. Watchdog Timer Management

- **Task not subscribed to TWDT before long operation** — if a task is subscribed to the Task Watchdog Timer (`esp_task_wdt_add(NULL)`) but runs a long computation without calling `esp_task_wdt_reset(NULL)`, the TWDT fires and reboots the device. Either shorten the operation, break it into yielding steps, or temporarily unsubscribe during the long operation.
  > Why: The TWDT timeout defaults to 5 seconds. Any task that holds the CPU continuously for longer without yielding triggers a reboot even if the task is making progress.

- **Raising watchdog timeout to suppress a symptom** — increasing `CONFIG_ESP_TASK_WDT_TIMEOUT_S` to stop watchdog resets is almost always wrong. The TWDT fires because a task is busy-waiting or stuck. Fix the root cause.
  > Why: A longer timeout delays the reboot but does not fix the starvation or lock-up that triggered it. In production, the device will still freeze; it just takes longer to reboot, making the user experience worse.

- **Critical section too wide triggers IWDT** — the Interrupt Watchdog Timer (IWDT) fires when interrupts are blocked for longer than ~0.3 seconds (default). A `portENTER_CRITICAL()` block that includes I2C transactions, flash reads, or UART writes will trigger the IWDT.
  > Why: The IWDT is the last line of defense against ISR starvation. Unlike the TWDT, an IWDT panic is not recoverable via task restructuring — it requires shrinking the critical section.

- **Idle task not given CPU time** — on each core, FreeRTOS runs an idle task that resets the TWDT and performs memory cleanup (`pvPortFree` deferred calls). A task at priority > 0 that never blocks starves the idle task, causing TWDT to fire even if the task is not "stuck".
  > Why: The TWDT monitors the idle task's execution, not individual application tasks. Starving the idle task looks identical to a hung task from the watchdog's perspective.

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
