# ESP-IDF v6.0 Breaking Changes — Auditor Quick Reference

This file is a fast-reference for the `update-skill` auditor. When auditing
`code-review` reference docs against ESP-IDF v6.0 (the version used in this
project), check each section below before running web searches — these are
confirmed breaking changes that affect the skill's domain.

Source: [ESP-IDF v6.0 Migration Guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/migration-guides/release-6.x/6.0/)

---

## Peripheral Driver Removals (Completely Removed in v6.0)

The following legacy drivers were *completely removed* in v6.0 (they were
deprecated since v5.0 and now produce compile errors — not warnings):

| Legacy header | Replacement header | Component |
|---|---|---|
| `driver/timer.h` | `driver/gptimer.h` | `esp_driver_gptimer` |
| `driver/pcnt.h` | `driver/pulse_cnt.h` | `esp_driver_pcnt` |
| `driver/i2s.h` | `driver/i2s_std.h` / `driver/i2s_tdm.h` | `esp_driver_i2s` |
| `driver/adc.h` (legacy) | `esp_adc/adc_oneshot.h` | `esp_adc` |
| `driver/rmt.h` (legacy) | `driver/rmt_tx.h` / `driver/rmt_rx.h` | `esp_driver_rmt` |
| `driver/mcpwm.h` (legacy) | `driver/mcpwm_prelude.h` | `esp_driver_mcpwm` |

**EOL (not yet removed, but End-of-Life — no fixes, will be removed in v7.0):**
- `driver/i2c.h` — migrate to `driver/i2c_master.h` or `driver/i2c_slave.h`

---

## System / libc Changes

### Picolibc replaces Newlib as the default libc
- **Removed:** `<sys/signal.h>` — replace with `<signal.h>`
- **Removed:** per-task `stdin`/`stdout`/`stderr` redirection (were task-local with Newlib; now global)
- **Binary size:** smaller by ~6% on average; stack consumption reduced for I/O operations
- **Revert if needed:** `menuconfig → Component config → C library → Newlib`

### EXT_RAM_ATTR macro removed
- `EXT_RAM_ATTR` was deprecated since v5.0; **removed in v6.0**
- Replacement: `EXT_RAM_BSS_ATTR` (for zero-initialized `.bss` in PSRAM)
- Also available: `EXT_RAM_NOINIT_ATTR` (for non-initialized PSRAM data)
- Also removed: `esp_spiram.h` header — use `esp_psram.h` instead

---

## FreeRTOS API Changes

### Task notification functions are now macros
`ulTaskNotifyTake()` and `xTaskNotifyWait()` changed from standalone functions
to macros in v6.0. This breaks any code that:
- Takes a function pointer to these APIs
- Uses them in a `sizeof()` or `_Generic()` context
- Explicitly casts their type

Standard call-site usage (`ulTaskNotifyTake(pdTRUE, portMAX_DELAY)`) is
unaffected — the macro expands correctly.

---

## I2C Slave Driver Change

The I2C slave v1 driver was removed in v6.0. Use `driver/i2c_slave.h` (the new
slave driver, available since v5.1).

---

## mbedTLS Certificate Bundle

Deprecated CA certificates were removed from the default bundle. Firmware
built with v6.0 may fail to connect to endpoints relying on those CAs. Test
all TLS endpoints before deploying v6.0-based firmware.

---

## Searching for These Issues in Code Review

When the `code-review` skill reference docs mention any of the items above,
verify they reflect the v6.0 status. Good search queries:

```
legacy timer group driver removed ESP-IDF v6.0 gptimer migration
legacy PCNT driver removed v6.0 pulse_cnt.h ESP-IDF
i2c.h EOL end-of-life v7.0 removal migration i2c_master.h
EXT_RAM_ATTR removed PSRAM EXT_RAM_BSS_ATTR ESP-IDF v6
Picolibc Newlib default libc ESP-IDF v6.0 sys/signal.h per-task stdio
ulTaskNotifyTake macro v6.0 function pointer FreeRTOS ESP-IDF
```
