/** @odoo-module **/

// ensure mail mock server is loaded first.
import "@mail/../tests/helpers/mock_server";

import {MockServer} from "@web/../tests/helpers/mock_server";
import {patch} from "@web/core/utils/patch";

patch(MockServer.prototype, "ai_oca_bridge", {
    async _performRPC(route, args) {
        if (args.model === "ai.bridge" && args.method === "execute_ai_bridge") {
            const record = this.models["ai.bridge"].records.filter(
                (record) => record.id === args.args[0][0]
            );
            if (record && record[0].result_type === "action") {
                return {
                    action: {
                        type: "ir.actions.act_window",
                        res_model: "res.partner",
                        views: [[false, "tree"]],
                    },
                };
            }
            return {
                notification: {
                    body: "Mocked AI Bridge Response",
                    args: {
                        type: "info",
                        title: "AI Bridge Notification",
                    },
                },
            };
        }
        return this._super(...arguments);
    },
});
