/** @odoo-module **/

import {registerPatch} from "@mail/model/model_core";

registerPatch({
    name: "Chatter",
    recordMethods: {
        async onClickAiBridge(aiBridge) {
            if (this.isTemporary) {
                const saved = await this.doSaveRecord();
                if (!saved) {
                    return;
                }
            }
            const notification = await this.env.services.orm.call(
                "ai.bridge",
                "execute_ai_bridge",
                [[aiBridge.id], this.thread.model, this.thread.id]
            );
            if (notification && this.env.services && this.env.services.notification) {
                this.env.services.notification.add(
                    notification.body,
                    notification.args
                );
            }
        },
    },
});
