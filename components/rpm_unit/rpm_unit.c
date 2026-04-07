#include "rpm_unit.h"

// timer callback forward declaration for the rpm unit component
static void rpm_timer_cb(void *arg);

static const char *TAG = "RPM_UNIT";

// Sample window for RPM measurement: 200,000 microseconds = 200 ms.
#define RPM_SAMPLE_US      200000

// GPIO used for the Hall sensor digital output.
// On ESP32-S3-DevKitC-1 v1.0, GPIO42 is J3 pin 6.
#define HALL_GPIO          GPIO_NUM_42

// Handle to the PCNT "unit" (counter instance).
// The new driver represents PCNT resources with opaque handles.
static pcnt_unit_handle_t s_pcnt_unit = NULL;

void hall_rpm_init(void)
{
    // Handle for the PCNT channel inside the PCNT unit.
    pcnt_channel_handle_t pcnt_chan = NULL;

    // low_limit and high_limit define the valid signed count range.
    pcnt_unit_config_t unit_config = {
        .low_limit = -1,
        .high_limit = 10000, // the uper limit of the counting
    };
    // allocate the new PCNT unit
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_config, &s_pcnt_unit));

    // PCNT channel configuration:
    // edge_gpio_num  = the GPIO where pulses arrive
    // level_gpio_num = optional control signal GPIO
    //
    // For simple pulse counting we do not need the level/control input,
    // so we set it to -1 (unused / virtual).
    pcnt_chan_config_t chan_config = {
        .edge_gpio_num = HALL_GPIO,
        .level_gpio_num = -1,
    };

    // Allocate a channel inside the unit and bind it to our Hall GPIO.
    ESP_ERROR_CHECK(pcnt_new_channel(s_pcnt_unit, &chan_config, &pcnt_chan));

    // Set edge functionality
    // This code assumes the module idles HIGH and goes LOW when the magnet is detected.
    // In that case:
    //   rising edge  = do nothing
    //   falling edge = increment the count
        ESP_ERROR_CHECK(pcnt_channel_set_edge_action(
        pcnt_chan,
        PCNT_CHANNEL_EDGE_ACTION_HOLD,      // on rising edge: don't change the count
        PCNT_CHANNEL_EDGE_ACTION_INCREASE   // on falling edge: count +1
    ));

    // Configure the built-in glitch filter.
    // max_glitch_ns means:
    //   any pulse shorter than this threshold is treated as noise and ignored.
    //
    // 1000 ns = 1 us is a reasonable first guess.
    // If the signal is noisy, you can try 2000 or 5000 ns later.
    pcnt_glitch_filter_config_t filter_config = {
        .max_glitch_ns = 1000,
    };

    // The PCNT docs say the glitch filter should be set while the unit is still
    // in the init state, i.e. before pcnt_unit_enable().
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(s_pcnt_unit, &filter_config));

    // Enable the PCNT unit so it becomes operational.
    ESP_ERROR_CHECK(pcnt_unit_enable(s_pcnt_unit));

    // Start the count from the value zero.
    ESP_ERROR_CHECK(pcnt_unit_clear_count(s_pcnt_unit));

    // Start the counter so incoming Hall pulses are counted in hardware.
    ESP_ERROR_CHECK(pcnt_unit_start(s_pcnt_unit));

    // Describe the periodic  software timer that will read the PCNT count.
    const esp_timer_create_args_t timer_args = {
        .callback = &rpm_timer_cb,          // function called on every timer tick
        .arg = NULL,                     // no custom argument needed
        .dispatch_method = ESP_TIMER_TASK,  // run callback in ESP timer task (simple and safe here)
        .name = "rpm_callback",             // friendly debug name
        .skip_unhandled_events = true,      // avoid piling up callbacks if the system is delayed
    };

        // Will receive the created timer handle.
    esp_timer_handle_t rpm_timer = NULL;

    // Create the timer object.
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &rpm_timer));

    // Start the timer as a periodic timer with a 200 ms period.
    ESP_ERROR_CHECK(esp_timer_start_periodic(rpm_timer, RPM_SAMPLE_US));

    // Log success.
    ESP_LOGI(TAG, "Hall RPM measurement started on GPIO %d", HALL_GPIO);

}


//-----------------------------------------------------------------------------------------
//-----------------------------------------------------------------------------------------
//-----------------------------------------------------------------------------------------




// Latest raw pulse count from the most recent 200 ms measurement window.
static volatile int s_last_pulses_200ms = 0;

// Sum of pulses across 5 x 200 ms samples = 1 second total.
// We use this to get a smoother once-per-second RPM value.
static volatile int s_pulse_sum_1s = 0;

// Counts how many 200 ms samples have been accumulated so far.
static volatile int s_sample_count = 0;

// Number of Hall pulses generated per one full shaft revolution.
// If you use one magnet, this is 1.0f.
// If you later use two magnets, change this to 2.0f.
#define PULSES_PER_REV     1.0f

//--------------------------------------------------------------------------------

// Flag set by the timer callback when a fresh 1-second RPM value is ready.
extern volatile bool s_rpm_ready_1s;

// Final RPM value computed once per second.
extern volatile float s_rpm_1s;

/**
 * Timer callback that runs every 200 ms.
 *
 * The job here is intentionally small:
 *   1) read the current pulse count from PCNT
 *   2) clear the count for the next 200 ms window
 *   3) accumulate 5 windows into a 1-second RPM result
 *
 * We keep this callback short because timer callbacks should stay lightweight.
 */
static void rpm_timer_cb(void *arg)
{
    // Holds the number of pulses counted during the last 200 ms window.
    int pulses = 0;

    // Read the current PCNT count into 'pulses'.
    // Because PCNT counts in hardware, this value was accumulated while the CPU did other work.
    (void)pcnt_unit_get_count(s_pcnt_unit, &pulses);

    // Clear the count so the next 200 ms window starts from zero.
    (void)pcnt_unit_clear_count(s_pcnt_unit);

    // Save the last raw 200 ms sample in case you want to inspect/debug it later.
    s_last_pulses_200ms = pulses;

    // Add this 200 ms sample into the rolling 1-second sum.
    s_pulse_sum_1s += pulses;

    // Count how many 200 ms windows we have accumulated.
    s_sample_count++;

    // After 5 windows, we have 1 second of data.
    if (s_sample_count >= 5) {

        // In 1 second, "pulses per second" is simply the total pulse count.
        // RPM = pulses_per_second * 60 / pulses_per_revolution
        //
        // Example with 1 magnet:
        //   50 pulses in 1 second -> 50 rev/s -> 3000 RPM
        s_rpm_1s = (s_pulse_sum_1s * 60.0f) / PULSES_PER_REV;

        // Reset the accumulator for the next 1-second block.
        s_pulse_sum_1s = 0;

        // Reset sample counter back to 0.
        s_sample_count = 0;

        // Tell the main loop that a new RPM result is ready to print.
        s_rpm_ready_1s = true;
    }
}
