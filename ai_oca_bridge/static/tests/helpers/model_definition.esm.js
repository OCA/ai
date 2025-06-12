/** @odoo-module **/

import {
    addModelNamesToFetch,
    insertModelFields,
    insertRecords,
} from "@bus/../tests/helpers/model_definitions_helpers";

addModelNamesToFetch(["ai.bridge"]);

insertModelFields("res.partner", {
    ai_bridge_info: {default: [], type: "json"},
});
insertModelFields("ai.bridge", {
    result_type: {
        default: "none",
        type: "selection",
        selection: [
            ["none", "None"],
            ["action", "Action"],
            ["notification", "Notification"],
        ],
    },
    name: {string: "Name", type: "char"},
});
insertRecords("ai.bridge", [
    {id: 1, name: "Test AI Bridge", result_type: "none"},
    {id: 2, name: "Test AI Bridge Action", result_type: "action"},
]);
