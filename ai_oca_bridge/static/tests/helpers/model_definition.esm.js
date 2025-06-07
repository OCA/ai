/** @odoo-module **/

import {insertModelFields} from "@bus/../tests/helpers/model_definitions_helpers";

insertModelFields("res.partner", {
    ai_bridge_info: {default: [], type: "json"},
});
