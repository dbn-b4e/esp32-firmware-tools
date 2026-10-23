#pragma once
#include <stdint.h>
namespace demo {
// GPIO2 is the discrete LED on the relay C6 board used for this example.
// This is NOT an addressable RGB/WS2812 driver. Adapt to your actual board.
constexpr uint8_t kLedPin=2;
constexpr bool kLedActiveLow=false;
constexpr uint8_t kBootPin=9;
static_assert(kLedPin!=kBootPin,"LED and BOOT pins must be distinct");
static_assert(kLedPin!=12 && kLedPin!=13 && kBootPin!=12 && kBootPin!=13,"Preserve native USB GPIO12/13");
}
