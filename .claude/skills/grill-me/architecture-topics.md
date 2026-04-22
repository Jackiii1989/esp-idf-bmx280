# Architecture Review Topics

Cover in order. Skip if already resolved.

---

## 1. Synchronization model
Probe: polling flag vs. blocking semaphore/queue — why?
Agreed: SPSC → polling fine. 20ms sleep keeps CPU idle. Worst failure = skipped print. Semaphore adds overhead with no benefit at this scale.

## 2. Data ownership
Probe: `extern volatile` in component writing into caller's variables — who owns it?
Agreed: component using `extern` does NOT own the variable. Anti-pattern. Fix: component owns state as `static`, exposes getter.

## 3. Error handling strategy
Probe: abort+reboot on sensor failure vs. graceful recovery — which and why?
Agreed: `ESP_ERROR_CHECK` in `app_main` = correct for dev (loud failures). Driver must always return `esp_err_t`; caller decides policy. Production needs reporting channel (MQTT/BLE/HTTP).

## 4. Peripheral lifecycle
Probe: no deinit — intentional? What breaks if init called twice?
Agreed: reboot-on-fault design makes missing deinit acceptable. But lost timer handle = second init doubles callback rate silently. Fix: promote handle to `static`. One line, zero cost.

## 5. Timing and scheduling
Probe: `isSampling()` loop — what if it never returns false?
Agreed: no timeout is a gap. Each call = full I2C tx. Bus freeze → infinite block, no log. Fix: 50ms timeout + `ESP_LOGW`.

## 6. Component boundaries
Probe: public header — leaks internal types/deps?
Agreed: *(not covered)*

## 7. Output format and protocol
Probe: CSV field order stable? Matches consumer?
Agreed: *(not covered)*

## 8. Testing and observability
Probe: how do you verify correctness without hardware?
Agreed: *(not covered)*
