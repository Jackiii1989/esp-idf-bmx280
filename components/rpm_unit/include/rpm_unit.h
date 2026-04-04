#ifndef _RPM_UNIT_H_
#define _RPM_UNIT_H_

#include <stdio.h>
#include "esp_log.h"
#include "driver/pulse_cnt.h"
#include "esp_timer.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#ifdef __cplusplus
extern "C" {
#endif

void hall_rpm_init(void);

#ifdef __cplusplus
};
#endif


#endif