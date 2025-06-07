/** @odoo-module **/

// ensure mail mock server is loaded first.
import "@mail/../tests/helpers/mock_server";

import {MockServer} from "@web/../tests/helpers/mock_server";
import {patch} from "@web/core/utils/patch";

patch(MockServer.prototype, "ai_oca_bridge", {
    async _performRPC(route, args) {
        if (args.model === "ai.bridge" && args.method === "execute_ai_bridge") {
            return {
                body: "Mocked AI Bridge Response",
                args: {
                    type: "info",
                    title: "AI Bridge Notification",
                },
            };
        }
        return this._super(...arguments);
    },
});
