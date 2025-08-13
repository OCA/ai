/** @odoo-module **/

import {MockServer} from "@web/../tests/helpers/mock_server";
import {patch} from "@web/core/utils/patch";

patch(MockServer.prototype, {
    async performRPC(route, args) {
        if (args.model === "ai.bridge" && args.method === "execute_ai_bridge") {
            const record = this.models["ai.bridge"].records.filter(
                (r) => r.id === args.args[0][0]
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
        return await super.performRPC(...arguments);
    },
});
