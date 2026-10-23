#pragma once
#include <Zigbee.h>
namespace demo {
// Arduino ESP32 3.3.4 reportTemperature/reportBinaryInput leave bitfields
// uninitialized. Build a complete standard ZCL request locally; no core patch.
inline bool reportStandardAttribute(uint8_t endpoint,uint16_t cluster,uint16_t attribute){
 esp_zb_zcl_report_attr_cmd_t command{};
 command.address_mode=ESP_ZB_APS_ADDR_MODE_DST_ADDR_ENDP_NOT_PRESENT;
 command.zcl_basic_cmd.src_endpoint=endpoint;
 command.clusterID=cluster;command.attributeID=attribute;
 command.direction=ESP_ZB_ZCL_CMD_DIRECTION_TO_CLI;
 command.manuf_specific=0;
 command.manuf_code=ESP_ZB_ZCL_ATTR_NON_MANUFACTURER_SPECIFIC;
 esp_zb_lock_acquire(portMAX_DELAY);
 esp_err_t result=esp_zb_zcl_report_attr_cmd_req(&command);
 esp_zb_lock_release();
 return result==ESP_OK;
}
}
