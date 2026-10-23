import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {prepareDefinition} from 'zigbee-herdsman-converters';

const here=dirname(fileURLToPath(import.meta.url));
const root=resolve(here,'../..');
const python=process.env.PYTHON || (process.platform==='win32'?'python':'python3');
mkdirSync(join(here,'tmp'),{recursive:true});
const directory=mkdtempSync(join(here,'tmp/case-'));
const descriptor=JSON.parse(readFileSync(join(root,'examples/c6-zigbee-demo/descriptor.example.json'),'utf8'));
async function create(value,name){
    const input=join(directory,name+'.json'),output=join(directory,name+'.mjs');
    writeFileSync(input,JSON.stringify(value));
    const result=spawnSync(python,[join(root,'z2m/converter.py'),'generate','--input',input,'--output',output],{encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    return (await import(pathToFileURL(output).href)).default;
}
const raw=await create(descriptor,'normal');
const definition=prepareDefinition(raw);
const endpoints=[10,20,30].map(ID=>({ID}));
const device={endpoints,getEndpoint:id=>endpoints.find(e=>e.ID===id)};
const meta={device,mapped:definition,options:{},state:{},message:{}};
const convert=(cluster,ID,data)=>{
    const converter=definition.fromZigbee.find(c=>c.cluster===cluster && c.type.includes('attributeReport'));
    assert.ok(converter,'Missing converter '+cluster);
    return converter.convert(definition,{cluster,type:'attributeReport',endpoint:device.getEndpoint(ID),data},()=>{}, {},meta);
};
test('real modernExtend produces the expected HA-facing properties',()=>{
    assert.deepEqual(definition.endpoint(device),{led:10,boot:20,simulated:30});
    assert.deepEqual(raw.fingerprint,[{modelID:'C6-TOOLS-DEMO',manufacturerName:'Example'}]);
    const exposes=definition.exposes.flatMap(e=>e.features||[e]);
    assert.deepEqual(exposes.map(e=>e.property).sort(),['pressed_boot','state_led','temperature_simulated']);
    const input=exposes.find(e=>e.property==='pressed_boot');assert.equal(input.access,5);
    assert.equal(exposes.find(e=>e.property==='temperature_simulated').unit,'°C');
    assert.equal(definition.toZigbee.find(c=>c.key.includes('pressed')).convertSet,undefined);
});
test('actual converters decode LED, BOOT and temperature Zigbee reports',()=>{
    assert.equal(convert('genOnOff',10,{onOff:1}).state_led,'ON');
    assert.equal(convert('genBinaryInput',20,{presentValue:1}).pressed_boot,true);
    assert.equal(convert('genBinaryInput',20,{presentValue:0}).pressed_boot,false);
    assert.equal(convert('msTemperatureMeasurement',30,{measuredValue:2134}).temperature_simulated,21.34);
});
test('LED command uses genOnOff while the input remains read-only',async()=>{
    const sent=[];const entity={...device.getEndpoint(10),command:async(...args)=>sent.push(args)};
    const converter=definition.toZigbee.find(c=>c.key.includes('state'));
    await converter.convertSet(entity,'state','ON',{...meta,endpoint_name:'led',message:{state:'ON'}});
    assert.equal(sent.length,1);assert.equal(sent[0][0],'genOnOff');assert.equal(sent[0][1],'on');
});
test('descriptor strings cannot execute JavaScript',async()=>{
    const evil=structuredClone(descriptor);evil.device.description='";globalThis.descriptorInjected=true;//';
    const value=await create(evil,'quoted');assert.equal(value.description,evil.device.description);
    assert.equal(globalThis.descriptorInjected,undefined);
});
process.on('exit',()=>rmSync(directory,{recursive:true,force:true}));
