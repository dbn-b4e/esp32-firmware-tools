// MIT. Standalone C6 demonstration using the installed Arduino Zigbee API.
#ifndef ZIGBEE_MODE_ED
#error "Select Zigbee end-device mode"
#endif
#include <Arduino.h>
#include <Zigbee.h>
#include <atomic>
#include "board_config.h"
#include "descriptor.h"

ZigbeeLight led(demo::kFeatures[0].endpoint);
ZigbeeBinary boot(demo::kFeatures[1].endpoint);
ZigbeeTempSensor temperature(demo::kFeatures[2].endpoint);
std::atomic<bool> desiredLed{false},appliedLed{false},pressedBoot{false},connected{false},reportingReady{false};
std::atomic<int> temperatureCenti{2000};

// Callback can run in the Zigbee task. Only applicationTask writes the GPIO.
void ledCommand(bool value){desiredLed.store(value);}

bool initializeReporting(){
 esp_zb_zcl_reporting_info_t r{};
 r.direction=ESP_ZB_ZCL_CMD_DIRECTION_TO_SRV;r.ep=demo::kFeatures[1].endpoint;
 r.cluster_id=ESP_ZB_ZCL_CLUSTER_ID_BINARY_INPUT;r.cluster_role=ESP_ZB_ZCL_CLUSTER_SERVER_ROLE;
 r.attr_id=ESP_ZB_ZCL_ATTR_BINARY_INPUT_PRESENT_VALUE_ID;
 r.u.send_info.min_interval=demo::kBootMinSeconds;r.u.send_info.max_interval=demo::kBootMaxSeconds;
 r.u.send_info.def_min_interval=demo::kBootMinSeconds;r.u.send_info.def_max_interval=demo::kBootMaxSeconds;
 r.u.send_info.delta.u8=1;r.dst.profile_id=ESP_ZB_AF_HA_PROFILE_ID;r.manuf_code=ESP_ZB_ZCL_ATTR_NON_MANUFACTURER_SPECIFIC;
 esp_zb_lock_acquire(portMAX_DELAY);auto result=esp_zb_zcl_update_reporting_info(&r);esp_zb_lock_release();
 bool temp=temperature.setReporting(demo::kTempMinSeconds,demo::kTempMaxSeconds,demo::kTempChangeCenti/100.0f);
 return result==ESP_OK && temp;
}

void applicationTask(void*){
 bool lastRaw=false,stable=false,bootDirty=true,wasConnected=false,reportAttempted=false;
 uint32_t changedAt=millis(),lastTemp=0,lastBoot=0,lastReporting=0;unsigned phase=0;
 for(;;){
  uint32_t now=millis();bool raw=digitalRead(demo::kBootPin)==LOW;
  if(raw!=lastRaw){lastRaw=raw;changedAt=now;}
  if(raw!=stable && uint32_t(now-changedAt)>=30){stable=raw;pressedBoot.store(stable);bootDirty=true;}
  bool output=desiredLed.load();
  if(output!=appliedLed.load()){
   digitalWrite(demo::kLedPin,(output!=demo::kLedActiveLow)?HIGH:LOW);appliedLed.store(output);
  }
  if(Zigbee.started() && !reportingReady.load() && (!reportAttempted || uint32_t(now-lastReporting)>=5000)){
   reportAttempted=true;lastReporting=now;reportingReady.store(initializeReporting());
  }
  bool online=Zigbee.connected();connected.store(online);
  if(online && reportingReady.load()){
   bool first=!wasConnected;
   if(first || (bootDirty && uint32_t(now-lastBoot)>=1000) || uint32_t(now-lastBoot)>=30000){
    lastBoot=now;bool set=boot.setBinaryInput(stable);bool sent=boot.reportBinaryInput();bootDirty=!(set&&sent);
   }
   if(first || uint32_t(now-lastTemp)>=5000){
    lastTemp=now;int value=2000+int(phase<=50?phase:100-phase)*10;phase=(phase+1)%100;
    temperatureCenti.store(value);temperature.setTemperature(value/100.0f);temperature.reportTemperature();
   }
  }
  wasConnected=online;vTaskDelay(pdMS_TO_TICKS(10));
 }
}

void command(const char* line){
 if(!strcmp(line,"describe")){
  Serial.print("Z2M_DESCRIPTOR ");demo::writeDescriptor(Serial);Serial.println();
 }else if(!strcmp(line,"status")){
  Serial.printf("{\"version\":%u,\"zigbee\":%s,\"reporting_ready\":%s,\"led\":%s,\"boot\":%s,\"temperature_centi\":%d}\n",
   EXAMPLE_FW_VERSION,connected.load()?"true":"false",reportingReady.load()?"true":"false",
   appliedLed.load()?"true":"false",pressedBoot.load()?"true":"false",temperatureCenti.load());
 }else if(!strcmp(line,"help"))Serial.println("help | status | describe ; LED commands are received over Zigbee");
 else if(*line)Serial.println("Unknown command; use help");
}
void pollConsole(){
 static char line[64];static size_t used=0;static bool overflow=false;
 while(Serial.available()){
  char c=char(Serial.read());if(c=='\r')continue;
  if(c=='\n'){
   if(!overflow){line[used]=0;command(line);}else Serial.println("Command too long");
   used=0;overflow=false;
  }else if(used<sizeof(line)-1 && !overflow)line[used++]=c;
  else overflow=true;
 }
}
void setup(){
 Serial.begin(115200);pinMode(demo::kLedPin,OUTPUT);
 digitalWrite(demo::kLedPin,demo::kLedActiveLow?HIGH:LOW);pinMode(demo::kBootPin,INPUT_PULLUP);
 led.setManufacturerAndModel(demo::kManufacturer,demo::kModel);led.onLightChange(ledCommand);
 boot.setManufacturerAndModel(demo::kManufacturer,demo::kModel);
 temperature.setManufacturerAndModel(demo::kManufacturer,demo::kModel);
 temperature.setMinMaxValue(-10,50);
 if(!boot.addBinaryInput() || !Zigbee.addEndpoint(&led) || !Zigbee.addEndpoint(&boot) || !Zigbee.addEndpoint(&temperature)){
  Serial.println("Endpoint registration failed; console remains available");return;
 }
 Zigbee.setRxOnWhenIdle(true);Zigbee.setTimeout(10000);
 bool ready=Zigbee.begin(ZIGBEE_END_DEVICE,false); // Keep existing association; no implicit reset.
 Serial.printf("Zigbee begin=%d started=%d; help/status/describe available\n",ready,Zigbee.started());
 if(xTaskCreate(applicationTask,"demo",8192,nullptr,1,nullptr)!=pdPASS)Serial.println("Application task creation failed");
}
void loop(){pollConsole();delay(5);}
