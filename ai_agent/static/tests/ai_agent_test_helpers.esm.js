import {mailModels} from "@mail/../tests/mail_test_helpers";
import {mailDataHelpers} from "@mail/../tests/mock_server/mail_mock_server";

import {
    Command,
    defineModels,
    fields,
    getKwArgs,
    makeKwArgs,
    models,
    serverState,
} from "@web/../tests/web_test_helpers";

export class DiscussChannel extends mailModels.DiscussChannel {
    ai_agent_id = fields.Many2one({relation: "ai.agent"});
    ai_res_model = fields.Char();
    ai_res_id = fields.Integer();
    ai_context = fields.Generic();

    /** @override */
    _channel_basic_info(ids) {
        const data = super._channel_basic_info(...arguments);
        const [channel] = this.browse(ids);
        if (channel.channel_type === "ai_agent") {
            const [document] = channel.ai_res_id
                ? this.env[channel.ai_res_model].browse(channel.ai_res_id)
                : [];
            Object.assign(data, {
                ai_agent_id: channel.ai_agent_id,
                ai_res_model: channel.ai_res_model || false,
                ai_res_id: channel.ai_res_id || false,
                ai_res_display_name: document?.display_name || document?.name || false,
                ai_context: channel.ai_context || false,
            });
        }
        return data;
    }
}

export class AiAgent extends models.ServerModel {
    _name = "ai.agent";

    name = fields.Char();
    user_id = fields.Many2one({relation: "res.users"});

    _partner(agent) {
        return this.env["res.users"].browse(agent.user_id)[0].partner_id;
    }

    _sessions(agent) {
        return this.env["discuss.channel"]
            .search_read([
                ["channel_type", "=", "ai_agent"],
                ["ai_agent_id", "=", agent.id],
            ])
            .sort((c1, c2) => c2.id - c1.id)
            .map((channel) => ({
                id: channel.id,
                name: channel.name,
                channel_id: channel.id,
                res_model: channel.ai_res_model || false,
                res_id: channel.ai_res_id || false,
                res_name: false,
                last_activity: channel.create_date,
            }));
    }

    get_sidebar_data() {
        return this.search_read([]).map((agent) => ({
            id: agent.id,
            name: agent.name,
            user_id: agent.user_id,
            partner_id: this._partner(agent),
            sessions: this._sessions(agent).slice(0, 5),
        }));
    }

    search_sessions() {
        const kwargs = getKwArgs(arguments, "agent_id", "term", "offset", "limit");
        const [agent] = this.browse(kwargs.agent_id);
        const sessions = this._sessions(agent).filter(
            (session) =>
                !kwargs.term ||
                session.name.toLowerCase().includes(kwargs.term.toLowerCase())
        );
        return {count: sessions.length, sessions};
    }

    action_start_conversation() {
        const kwargs = getKwArgs(
            arguments,
            "ids",
            "body",
            "res_model",
            "res_id",
            "in_chat_window",
            "view_context"
        );
        const [agent] = this.browse(kwargs.ids);
        /** @type {import("mock_models").DiscussChannel} */
        const DiscussChannel = this.env["discuss.channel"];
        const channelId = DiscussChannel.create({
            name: kwargs.body.slice(0, 40),
            channel_type: "ai_agent",
            group_public_id: false,
            ai_agent_id: agent.id,
            ai_res_model: kwargs.res_model || false,
            ai_res_id: kwargs.res_id || false,
            ai_context: kwargs.view_context || false,
            channel_member_ids: [
                Command.create({
                    partner_id: serverState.partnerId,
                    fold_state: kwargs.in_chat_window ? "open" : "closed",
                }),
                Command.create({partner_id: this._partner(agent)}),
            ],
        });
        DiscussChannel.message_post(
            channelId,
            makeKwArgs({
                body: kwargs.body,
                message_type: "comment",
                subtype_xmlid: "mail.mt_comment",
            })
        );
        return {
            channel_id: channelId,
            data: new mailDataHelpers.Store(
                DiscussChannel.browse(channelId)
            ).get_result(),
        };
    }
}

export function defineAiAgentModels() {
    return defineModels({...mailModels, DiscussChannel, AiAgent});
}

/**
 * Create an AI agent (with its user and partner) in the mock server.
 *
 * @returns {{ agentId: number, partnerId: number, userId: number }}
 */
export function createAgent(pyEnv, name = "Gemma") {
    const partnerId = pyEnv["res.partner"].create({name});
    const userId = pyEnv["res.users"].create({name, partner_id: partnerId});
    const agentId = pyEnv["ai.agent"].create({name, user_id: userId});
    return {agentId, partnerId, userId};
}

/** Create an existing AI agent conversation of the current user. */
export function createAgentChannel(pyEnv, agent, values = {}) {
    return pyEnv["discuss.channel"].create({
        name: "Capital de Francia",
        channel_type: "ai_agent",
        group_public_id: false,
        ai_agent_id: agent.agentId,
        channel_member_ids: [
            Command.create({partner_id: serverState.partnerId}),
            Command.create({partner_id: agent.partnerId}),
        ],
        ...values,
    });
}
