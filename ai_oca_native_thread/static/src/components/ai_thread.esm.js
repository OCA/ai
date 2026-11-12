/* Copyright 2026 Pierre Verkest
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).  */
import {Component, onWillStart, onWillUpdateProps, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class AiThread extends Component {
    setup() {
        this.orm = useService("orm");
        this.busService = useService("bus_service");

        this.busService.subscribe("ai_thread_update", (payload) => {
            if (payload.thread_id !== this.state.threadId) {
                return;
            }
            if (payload.status === "cancelled") {
                this.state.pendingJobs = 0;
                this.state.isLoading = false;
                return;
            }
            this._handleBusMessageUpdate(payload);
        });

        this.state = useState({
            messages: [],
            prompt: "",
            isLoading: false,
            pendingJobs: 0,
            threads: [],
            threadId: null,
        });

        onWillStart(async () => {
            await this.initConversations(
                this.props.threadModel,
                this.props.recordId,
                this.props.activeThreadId
            );
        });

        onWillUpdateProps(async (nextProps) => {
            if (
                nextProps.recordId !== this.props.recordId ||
                nextProps.threadModel !== this.props.threadModel ||
                nextProps.activeThreadId !== this.props.activeThreadId
            ) {
                this.state.prompt = "";
                this.state.messages = [];
                await this.initConversations(
                    nextProps.threadModel,
                    nextProps.recordId,
                    nextProps.activeThreadId
                );
            }
        });
    }

    _handleBusMessageUpdate(payload) {
        this.state.pendingJobs = Math.max(0, this.state.pendingJobs - 1);
        if (this.state.pendingJobs === 0) {
            this.state.isLoading = false;
        }
        if (payload.thread_name) {
            const threadItem = this.state.threads.find(
                (t) => t.id === payload.thread_id
            );
            if (threadItem) {
                threadItem.name = payload.thread_name;
            } else {
                this.state.threads.unshift({
                    id: payload.thread_id,
                    name: payload.thread_name,
                });
            }
        }
        if (payload.message) {
            const msgIndex = this.state.messages.findIndex(
                (m) => m.id === payload.message.id
            );
            if (msgIndex >= 0) {
                this.state.messages[msgIndex] = payload.message;
            } else {
                this.state.messages.push(payload.message);
            }
        } else if (payload.status === "error") {
            this.state.messages.push({
                role: "system",
                content: `Error: ${payload.content}`,
            });
        }
    }

    async fetchThreads(threadModel, recordId, threadId = null) {
        this.state.threads = await this.orm.searchRead(
            "ai.thread",
            [
                ["res_model", "=", threadModel],
                ["res_id", "=", recordId],
            ],
            ["id", "name"],
            {order: "create_date desc"}
        );
        if (threadId) {
            this.state.threadId = parseInt(threadId, 10);
        }
    }

    async initConversations(threadModel, recordId, activeThreadId = null) {
        this.state.threadId = null;
        this.state.messages = [];
        const targetId = activeThreadId || this.props.activeThreadId || null;
        await this.fetchThreads(threadModel, recordId, targetId);
        if (this.state.threadId) {
            await this.loadMessages();
        }
    }

    async onThreadChange(ev) {
        const selectedId = ev.target.value;
        if (selectedId === "new" || !selectedId) {
            this.state.threadId = null;
            this.state.messages = [];
        } else {
            this.state.threadId = parseInt(selectedId, 10);
            await this.loadMessages();
        }
    }

    async loadMessages() {
        if (!this.state.threadId) return;
        this.busService.addChannel(`ai_thread_${this.state.threadId}`);
        const messages = await this.orm.call("ai.thread", "get_full_messages", [
            this.state.threadId,
        ]);
        this.state.messages = messages;
        this.state.pendingJobs = await this.orm.call(
            "ai.thread",
            "get_pending_job_count",
            [this.state.threadId]
        );
    }

    async deleteCurrentThread() {
        if (!this.state.threadId) return;
        await this.orm.unlink("ai.thread", [this.state.threadId]);
        await this.initConversations(this.props.threadModel, this.props.recordId);
    }

    onKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            this.sendMessage();
        }
    }

    async sendMessage() {
        if (!this.state.prompt.trim()) return;

        const content = this.state.prompt;
        this.state.prompt = "";
        this.state.isLoading = true;
        this.state.pendingJobs += 1;

        // Optimistically add user message
        this.state.messages.push({role: "user", content: content, status: "done"});

        try {
            let isNew = false;
            let threadId = this.state.threadId;
            if (!threadId) {
                isNew = true;
                // Create thread if not exists
                const threadIds = await this.orm.create("ai.thread", [
                    {
                        res_model: this.props.threadModel,
                        res_id: this.props.recordId,
                    },
                ]);
                threadId = threadIds[0];
            }

            const response = await this.orm.call("ai.thread", "action_send_message", [
                threadId,
                content,
            ]);

            if (response.status === "pending") {
                this.busService.addChannel(`ai_thread_${threadId}`);
                if (response.assistant_message) {
                    this.state.messages.push(response.assistant_message);
                }
                if (response.thread_name) {
                    const threadItem = this.state.threads.find(
                        (t) => t.id === threadId
                    );
                    if (threadItem) {
                        threadItem.name = response.thread_name;
                    }
                }
                if (isNew) {
                    await this.fetchThreads(
                        this.props.threadModel,
                        this.props.recordId,
                        threadId
                    );
                }
            } else {
                this.state.isLoading = false;
                this.state.pendingJobs = Math.max(0, this.state.pendingJobs - 1);
                this.state.messages.push({
                    role: "system",
                    content: `Error: ${response.content || "Failed to start generation"}`,
                });
            }
        } catch (error) {
            console.error(
                "Failed to send AI message",
                error,
                error.message,
                error.data ? JSON.stringify(error.data) : ""
            );
            this.state.isLoading = false;
            this.state.pendingJobs = Math.max(0, this.state.pendingJobs - 1);
            this.state.messages.push({
                role: "system",
                content: `Network or Server Error.`,
            });
        }
    }

    async stopAi() {
        if (!this.state.threadId) return;
        await this.orm.call("ai.thread", "action_cancel_jobs", [this.state.threadId]);
    }
}

AiThread.template = "ai_oca_native_thread.AiThread";
AiThread.props = {
    threadModel: String,
    recordId: Number,
    activeThreadId: {optional: true},
};
