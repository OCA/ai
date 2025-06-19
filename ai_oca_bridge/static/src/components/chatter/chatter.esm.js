/** @odoo-module **/

import {registerPatch} from "@mail/model/model_core";

registerPatch({
    name: "Chatter",
    recordMethods: {
        async onClickAiBridge(aiBridge) {
            const saved = await this.doSaveRecord();
            if (!saved) {
                return;
            }
            const result = await this.env.services.orm.call(
                "ai.bridge",
                "execute_ai_bridge",
                [[aiBridge.id], this.thread.model, this.thread.id]
            );
            if (result.action && this.env.services && this.env.services.action) {
                this.env.services.action.doAction(result.action);
            } else if (
                result.notification &&
                this.env.services &&
                this.env.services.notification
            ) {
                this.env.services.notification.add(
                    result.notification.body,
                    result.notification.args
                );
            }
        },
    },
});
