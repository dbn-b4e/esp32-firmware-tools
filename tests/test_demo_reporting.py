"""Execute the actual firmware reporting helper against a minimal SDK boundary."""
import os,platform,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class DemoReporting(unittest.TestCase):
 def test_standard_reports_never_include_manufacturer_extension(self):
  header=ROOT/'examples/c6-zigbee-demo/sketch/reporting.h'
  self.assertTrue(header.exists(),'Safe report helper missing; Arduino 3.3.4 report methods leave manufacturer flags uninitialized')
  compiler=shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
  if not compiler:self.skipTest('Native C++ compiler unavailable')
  folder=ROOT/'tmp/reporting-test';folder.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=folder) as t:
   p=Path(t)
   (p/'Zigbee.h').write_text('''#include <stdint.h>
#include <assert.h>
constexpr int ESP_ZB_APS_ADDR_MODE_DST_ADDR_ENDP_NOT_PRESENT=0;
constexpr int ESP_ZB_ZCL_CMD_DIRECTION_TO_CLI=1;
constexpr int ESP_ZB_ZCL_ATTR_NON_MANUFACTURER_SPECIFIC=65535;
constexpr int ESP_OK=0,portMAX_DELAY=-1;
struct esp_zb_zcl_report_attr_cmd_t {
 struct {uint16_t dst_addr;uint8_t dst_endpoint,src_endpoint;} zcl_basic_cmd;
 int address_mode;uint16_t clusterID,attributeID;
 struct {uint8_t manuf_specific:2;uint8_t direction:1;uint8_t dis_default_resp:1;};
 uint16_t manuf_code;
};
using esp_err_t=int;
static int locks=0,commands=0,result=0;
static uint8_t expectedEndpoint;
static uint16_t expectedCluster,expectedAttribute;
inline void esp_zb_lock_acquire(int){assert(locks++==0);}
inline void esp_zb_lock_release(){assert(--locks==0);}
inline int esp_zb_zcl_report_attr_cmd_req(esp_zb_zcl_report_attr_cmd_t* c){
 assert(locks==1);assert(c->manuf_specific==0);assert(c->direction==1);
 assert(c->manuf_code==65535);assert(c->dis_default_resp==0);
 assert(c->address_mode==0);assert(c->zcl_basic_cmd.dst_addr==0);
 assert(c->zcl_basic_cmd.dst_endpoint==0);assert(c->zcl_basic_cmd.src_endpoint==expectedEndpoint);
 assert(c->clusterID==expectedCluster);assert(c->attributeID==expectedAttribute);++commands;return result;
}
''')
   src=p/'test.cpp';src.write_text('''#include "reporting.h"
int main(){
 expectedEndpoint=20;expectedCluster=15;expectedAttribute=85;
 assert(demo::reportStandardAttribute(20,15,85));
 expectedEndpoint=30;expectedCluster=1026;expectedAttribute=0;
 assert(demo::reportStandardAttribute(30,1026,0));
 result=1;assert(!demo::reportStandardAttribute(30,1026,0));
 assert(commands==3 && locks==0);
}
''')
   flags=['-std=c++17','-I'+str(p),'-I'+str(header.parent)]
   if platform.system()=='Darwin':flags+=['-isysroot',subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()]
   binary=p/('test.exe' if os.name=='nt' else 'test')
   subprocess.run([compiler,*flags,str(src),'-o',str(binary)],check=True,capture_output=True,timeout=30)
   subprocess.run([str(binary)],check=True,capture_output=True,timeout=5)
if __name__=='__main__':unittest.main()
