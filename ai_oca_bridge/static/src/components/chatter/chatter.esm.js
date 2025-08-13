/** @odoo-module **/

import {Chatter} from "@mail/core/web/chatter";
import {patch} from "@web/core/utils/patch";

patch(Chatter.prototype, {
    async onClickAiBridge(aiBridge) {
        let saved = true;

        if (this.props.webRecord && this.props.webRecord.save) {
            try {
                await this.props.webRecord.save();
            } catch (error) {
                saved = false;
                console.error("Error saving record:", error);
            }
        }

        if (!saved) {
            return;
        }

        const model = this.props.webRecord.resModel;
        const id = this.props.webRecord.resId;

        const result = await this.env.services.orm.call(
            "ai.bridge",
            "execute_ai_bridge",
            [[aiBridge.id], model, id]
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
});
