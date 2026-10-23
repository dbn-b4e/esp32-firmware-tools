// Generated from firmware capabilities; edit the firmware descriptor.
import * as m from 'zigbee-herdsman-converters/lib/modernExtend';

export default {
    fingerprint: [{"modelID": "C6-TOOLS-DEMO", "manufacturerName": "Example"}],
    model: "C6-TOOLS-DEMO",
    vendor: "Example",
    description: "BOOT input, LED output and simulated temperature",
    ota: false,
    extend: [
        m.deviceEndpoints({"endpoints": {"led": 10, "boot": 20, "simulated": 30}}),
        m.onOff({"endpointNames": ["led"], "powerOnBehavior": false, "configureReporting": true}),
        m.binary({"name": "pressed", "cluster": "genBinaryInput", "attribute": "presentValue", "valueOn": [true, 1], "valueOff": [false, 0], "access": "STATE_GET", "endpointName": "boot", "reporting": {"min": 0, "max": 60, "change": 1}}),
        m.temperature({"endpointNames": ["simulated"], "reporting": {"min": 5, "max": 60, "change": 10}})
    ],
};
