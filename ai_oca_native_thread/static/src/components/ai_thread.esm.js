import {Component, onWillStart, onWillUpdateProps, useState} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

export class AiThread extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            messages: [],
            prompt: "",
            isLoading: false,
            threads: [],
            threadId: null,
        });

        onWillStart(async () => {
            await this.initConversations(this.props.threadModel, this.props.recordId);
        });

        onWillUpdateProps(async (nextProps) => {
            if (
                nextProps.recordId !== this.props.recordId ||
                nextProps.threadModel !== this.props.threadModel
            ) {
                this.state.prompt = "";
                this.state.messages = [];
                this.state.threadId = null;
                await this.initConversations(nextProps.threadModel, nextProps.recordId);
            }
        });
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
        this.state.threadId = threadId;
    }

    async initConversations(threadModel, recordId) {
        this.state.threadId = null;
        this.state.messages = [];
        await this.fetchThreads(threadModel, recordId, null);
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
        const messages = await this.orm.searchRead(
            "ai.message",
            [["thread_id", "=", this.state.threadId]],
            ["role", "content"]
        );
        this.state.messages = messages;
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

        // Optimistically add user message
        this.state.messages.push({role: "user", content: content});

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

            if (response.status === "success") {
                this.state.messages.push({
                    role: "assistant",
                    content: response.content,
                });
                if (isNew) {
                    await this.fetchThreads(
                        this.props.threadModel,
                        this.props.recordId,
                        threadId
                    );
                }
            } else {
                this.state.messages.push({
                    role: "system",
                    content: `Error: ${response.content}`,
                });
            }
        } catch (error) {
            console.error("Failed to send AI message", error);
            this.state.messages.push({
                role: "system",
                content: `Network or Server Error.`,
            });
        } finally {
            this.state.isLoading = false;
        }
    }
}

AiThread.template = "ai_oca_native_thread.AiThread";
AiThread.props = {
    threadModel: String,
    recordId: Number,
};
