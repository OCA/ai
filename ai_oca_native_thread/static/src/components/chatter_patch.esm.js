/* Copyright 2026 Pierre Verkest
 * License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl). */
import {AiThread} from "./ai_thread.esm";
import {Chatter} from "@mail/chatter/web_portal/chatter";
import {patch} from "@web/core/utils/patch";
import {useState} from "@odoo/owl";

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.state) {
            this.state.aiMainTab = this.state.aiMainTab || "chatter";
        } else {
            this.state = useState({aiMainTab: "chatter"});
        }
    },
});

Chatter.components = {...Chatter.components, AiThread};
