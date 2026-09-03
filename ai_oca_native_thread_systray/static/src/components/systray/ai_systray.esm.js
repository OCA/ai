/* Copyright 2026 Pierre Verkest
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).  */
import {Component, onWillStart, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class AiSystray extends Component {
    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");
        this.actionService = useService("action");

        this.state = useState({
            threads: [],
            totalPending: 0,
            isOpen: false,
        });

        this.busService.subscribe("ai_thread_update", () => {
            this.loadActiveThreads();
        });

        onWillStart(async () => {
            await this.loadActiveThreads();
        });
    }

    async loadActiveThreads() {
        try {
            const threads = await this.orm.call(
                "ai.thread",
                "get_user_active_threads",
                []
            );
            this.state.threads = threads || [];
            this.state.totalPending = this.state.threads.reduce(
                (sum, t) =>
                    sum + (t.pending_jobs || (t.status === "processing" ? 1 : 0)),
                0
            );
        } catch (err) {
            console.error("Failed to load active AI threads for systray", err);
        }
    }

    toggleDropdown() {
        this.state.isOpen = !this.state.isOpen;
        if (this.state.isOpen) {
            this.loadActiveThreads();
        }
    }

    async openThreadRecord(thread) {
        this.state.isOpen = false;
        window.activeAiThreadTarget = {
            threadId: thread.id,
            resModel: thread.res_model,
            resId: thread.res_id,
        };
        this.env.bus.trigger("AI_THREAD:OPEN_THREAD", {
            threadId: thread.id,
            resModel: thread.res_model,
            resId: thread.res_id,
        });
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: thread.res_model,
            res_id: thread.res_id,
            views: [[false, "form"]],
            target: "current",
            context: {
                active_ai_thread_id: thread.id,
                active_ai_tab: true,
            },
        });
    }
}

AiSystray.template = "ai_oca_native_thread_systray.AiSystray";

export const aiSystrayItem = {
    Component: AiSystray,
};

registry.category("systray").add("ai_systray", aiSystrayItem, {sequence: 100});
