#pragma once
#include <stdint.h>
#include "version.h"
namespace demo {
enum class Kind {OnOff,BinaryInput,Temperature};
struct Feature {uint8_t endpoint;const char* name;Kind kind;};
constexpr char kModel[]="C6-TOOLS-DEMO";
constexpr char kManufacturer[]="Example";
constexpr char kDescription[]="BOOT input, LED output and simulated temperature";
constexpr Feature kFeatures[]={{10,"led",Kind::OnOff},{20,"boot",Kind::BinaryInput},{30,"simulated",Kind::Temperature}};
constexpr uint16_t kTempMinSeconds=5,kTempMaxSeconds=60,kTempChangeCenti=10;
constexpr uint16_t kBootMinSeconds=0,kBootMaxSeconds=60;
static_assert(sizeof(kModel)-1<=32 && sizeof(kManufacturer)-1<=32,"ZCL identity byte limits");
static_assert(sizeof(kFeatures)/sizeof(kFeatures[0])==3,"Update registration when adding capabilities");
static_assert(kFeatures[0].kind==Kind::OnOff && kFeatures[1].kind==Kind::BinaryInput && kFeatures[2].kind==Kind::Temperature,"Registration types must match exported capabilities");
static_assert(kFeatures[0].endpoint!=kFeatures[1].endpoint && kFeatures[0].endpoint!=kFeatures[2].endpoint && kFeatures[1].endpoint!=kFeatures[2].endpoint,"Unique endpoints required");
static_assert(kFeatures[0].endpoint>=1 && kFeatures[0].endpoint<=240 && kFeatures[1].endpoint>=1 && kFeatures[1].endpoint<=240 && kFeatures[2].endpoint>=1 && kFeatures[2].endpoint<=240,"HA endpoint range");
template<class Output>void quoted(Output& out,const char* text){
 const char* hex="0123456789abcdef";out.print('"');
 for(const unsigned char* p=reinterpret_cast<const unsigned char*>(text);*p;++p){
  if(*p=='"'||*p=='\\'){out.print('\\');out.print(static_cast<char>(*p));}
  else if(*p<32){out.print("\\u00");out.print(hex[*p>>4]);out.print(hex[*p&15]);}
  else out.print(static_cast<char>(*p));
 }
 out.print('"');
}
// The same identities/endpoints/constants below are used by the real Zigbee objects.
// Generic protocol only: no SSID, credentials, address, GPIO or infrastructure data.
template<class Output>void writeDescriptor(Output& out){
 out.print("{\"schema_version\":1,\"device\":{\"model\":");quoted(out,kModel);
 out.print(",\"manufacturer\":");quoted(out,kManufacturer);
 out.print(",\"description\":");quoted(out,kDescription);
 out.print(",\"firmware_version\":");out.print(static_cast<unsigned>(EXAMPLE_FW_VERSION));
 out.print("},\"ota\":false,\"endpoints\":[");
 for(unsigned i=0;i<3;++i){
  const auto& f=kFeatures[i];if(i)out.print(',');
  out.print("{\"id\":");out.print(static_cast<unsigned>(f.endpoint));out.print(",\"name\":");quoted(out,f.name);
  out.print(",\"clusters\":{\"input\":[0,3,");
  if(f.kind==Kind::OnOff)out.print("4,5,6");
  else out.print(static_cast<unsigned>(f.kind==Kind::BinaryInput?15:1026));
  out.print("],\"output\":[]},\"features\":[{\"type\":");
  quoted(out,f.kind==Kind::OnOff?"on_off":f.kind==Kind::BinaryInput?"binary_input":"temperature");
  if(f.kind==Kind::BinaryInput){
   out.print(",\"property\":\"pressed\",\"reporting\":{\"min\":");out.print(static_cast<unsigned>(kBootMinSeconds));
   out.print(",\"max\":");out.print(static_cast<unsigned>(kBootMaxSeconds));out.print(",\"change\":1}");
  }else if(f.kind==Kind::Temperature){
   out.print(",\"reporting\":{\"min\":");out.print(static_cast<unsigned>(kTempMinSeconds));
   out.print(",\"max\":");out.print(static_cast<unsigned>(kTempMaxSeconds));
   out.print(",\"change\":");out.print(static_cast<unsigned>(kTempChangeCenti));out.print('}');
  }
  out.print("}]}");
 }
 out.print("]}");
}
}
