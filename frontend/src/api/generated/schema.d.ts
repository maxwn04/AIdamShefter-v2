export interface paths {
    "/api/v1/competitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Competition List */
        get: operations["competition_list_api_v1_competitions_get"];
        put?: never;
        /** Create Competition */
        post: operations["create_competition_api_v1_competitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/competitions/{competition_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Competition Detail */
        get: operations["competition_detail_api_v1_competitions__competition_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Competition */
        patch: operations["update_competition_api_v1_competitions__competition_id__patch"];
        trace?: never;
    };
    "/api/v1/competitions/{competition_id}/seasons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Competition Season List */
        get: operations["competition_season_list_api_v1_competitions__competition_id__seasons_get"];
        put?: never;
        /** Create Competition Season */
        post: operations["create_competition_season_api_v1_competitions__competition_id__seasons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/competitions/{competition_id}/seasons/{season_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Competition Season Detail */
        get: operations["competition_season_detail_api_v1_competitions__competition_id__seasons__season_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/competitions/{competition_id}/seasons/{season_id}/roster-mappings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Roster Mappings */
        get: operations["get_roster_mappings_api_v1_competitions__competition_id__seasons__season_id__roster_mappings_get"];
        /** Put Roster Mappings */
        put: operations["put_roster_mappings_api_v1_competitions__competition_id__seasons__season_id__roster_mappings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data/competitions/{competition_id}/seasons/{season_id}/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get League Season Overview */
        get: operations["get_league_season_overview_api_v1_data_competitions__competition_id__seasons__season_id__overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data/competitions/{competition_id}/seasons/{season_id}/refreshes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Refreshes */
        get: operations["list_refreshes_api_v1_data_competitions__competition_id__seasons__season_id__refreshes_get"];
        put?: never;
        /** Run Manual Refresh */
        post: operations["run_manual_refresh_api_v1_data_competitions__competition_id__seasons__season_id__refreshes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data/competitions/{competition_id}/seasons/{season_id}/refreshes/{refresh_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Refresh */
        get: operations["get_refresh_api_v1_data_competitions__competition_id__seasons__season_id__refreshes__refresh_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/data/competitions/{competition_id}/seasons/{season_id}/snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Snapshots */
        get: operations["list_snapshots_api_v1_data_competitions__competition_id__seasons__season_id__snapshots_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation History */
        get: operations["generation_history_api_v1_generations_competitions__competition_id__get"];
        put?: never;
        /** Submit Generation */
        post: operations["submit_generation_api_v1_generations_competitions__competition_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation Detail */
        get: operations["generation_detail_api_v1_generations_competitions__competition_id___generation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/ai-calls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ai Call History */
        get: operations["ai_call_history_api_v1_generations_competitions__competition_id___generation_id__ai_calls_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/ai-calls/{ai_call_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ai Call Detail */
        get: operations["ai_call_detail_api_v1_generations_competitions__competition_id___generation_id__ai_calls__ai_call_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/article": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Submitted Article */
        get: operations["submitted_article_api_v1_generations_competitions__competition_id___generation_id__article_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact History */
        get: operations["artifact_history_api_v1_generations_competitions__competition_id___generation_id__artifacts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Detail */
        get: operations["artifact_detail_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/artifacts/{artifact_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Version History */
        get: operations["artifact_version_history_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/artifacts/{artifact_id}/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Version Detail */
        get: operations["artifact_version_detail_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/reruns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rerun Generation */
        post: operations["rerun_generation_api_v1_generations_competitions__competition_id___generation_id__reruns_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/tool-calls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tool Call History */
        get: operations["tool_call_history_api_v1_generations_competitions__competition_id___generation_id__tool_calls_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/tool-calls/{tool_call_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tool Call Detail */
        get: operations["tool_call_detail_api_v1_generations_competitions__competition_id___generation_id__tool_calls__tool_call_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/{generation_id}/usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation Usage */
        get: operations["generation_usage_api_v1_generations_competitions__competition_id___generation_id__usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/generations/competitions/{competition_id}/articles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Article History */
        get: operations["article_history_api_v1_generations_competitions__competition_id__articles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/context-notes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Context Note */
        post: operations["create_context_note_api_v1_memory_competitions__competition_id__context_notes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/context-notes/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Context Note */
        put: operations["replace_context_note_api_v1_memory_competitions__competition_id__context_notes__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/context-notes/{item_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Context Note History */
        get: operations["context_note_history_api_v1_memory_competitions__competition_id__context_notes__item_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/context-notes/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Context Note */
        get: operations["exact_context_note_api_v1_memory_competitions__competition_id__context_notes_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Event */
        post: operations["create_event_api_v1_memory_competitions__competition_id__events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/events/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Event */
        put: operations["replace_event_api_v1_memory_competitions__competition_id__events__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/events/{item_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Event History */
        get: operations["event_history_api_v1_memory_competitions__competition_id__events__item_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/events/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Event */
        get: operations["exact_event_api_v1_memory_competitions__competition_id__events_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/facts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Fact */
        post: operations["create_fact_api_v1_memory_competitions__competition_id__facts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/facts/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Fact */
        put: operations["replace_fact_api_v1_memory_competitions__competition_id__facts__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/facts/{item_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Fact History */
        get: operations["fact_history_api_v1_memory_competitions__competition_id__facts__item_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/facts/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Fact */
        get: operations["exact_fact_api_v1_memory_competitions__competition_id__facts_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Revision History */
        get: operations["revision_history_api_v1_memory_competitions__competition_id__revisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Revision */
        get: operations["exact_revision_api_v1_memory_competitions__competition_id__revisions__revision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/revisions/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Revision */
        get: operations["current_revision_api_v1_memory_competitions__competition_id__revisions_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Search Memory */
        post: operations["search_memory_api_v1_memory_competitions__competition_id__search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/storylines": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Storyline */
        post: operations["create_storyline_api_v1_memory_competitions__competition_id__storylines_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/storylines/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Storyline */
        put: operations["replace_storyline_api_v1_memory_competitions__competition_id__storylines__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/storylines/{item_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Storyline History */
        get: operations["storyline_history_api_v1_memory_competitions__competition_id__storylines__item_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/storylines/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Storyline */
        get: operations["exact_storyline_api_v1_memory_competitions__competition_id__storylines_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/triggers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Trigger */
        post: operations["create_trigger_api_v1_memory_competitions__competition_id__triggers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/triggers/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Trigger */
        put: operations["replace_trigger_api_v1_memory_competitions__competition_id__triggers__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/triggers/{item_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Trigger History */
        get: operations["trigger_history_api_v1_memory_competitions__competition_id__triggers__item_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/competitions/{competition_id}/triggers/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exact Trigger */
        get: operations["exact_trigger_api_v1_memory_competitions__competition_id__triggers_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Model Catalog */
        get: operations["model_catalog_api_v1_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Liveness
         * @description Report process liveness without touching the database.
         */
        get: operations["liveness_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Readiness
         * @description Report readiness only when bounded database checks pass.
         */
        get: operations["readiness_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AICall */
        AICall: {
            /** Actual Model */
            actual_model: string | null;
            /** Actual Provider */
            actual_provider: string | null;
            /** Attempt Number */
            attempt_number: number;
            /** Completed At */
            completed_at: string | null;
            /** Error */
            error: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Finish Reason */
            finish_reason: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Messages */
            input_messages: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            }[];
            /** Latency Ms */
            latency_ms: number | null;
            /** Provider Request Id */
            provider_request_id: string | null;
            /** Provider Response */
            provider_response: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Provider Response Id */
            provider_response_id: string | null;
            /** Request Parameters */
            request_parameters: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            };
            /** Requested Model */
            requested_model: string;
            /** Requested Provider */
            requested_provider: string | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["AICallStatus"];
            /** Tool Definitions */
            tool_definitions: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            }[];
            /** Turn Number */
            turn_number: number;
            usage: components["schemas"]["TokenUsage"];
        };
        /** AICallPage */
        AICallPage: {
            /** Items */
            items: components["schemas"]["AICallSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** AICallPageResponse */
        AICallPageResponse: {
            page: components["schemas"]["AICallPage"];
        };
        /** AICallResponse */
        AICallResponse: {
            ai_call: components["schemas"]["AICall"];
        };
        /**
         * AICallStatus
         * @enum {string}
         */
        AICallStatus: "started" | "succeeded" | "retryable_error" | "fatal_error" | "cancelled" | "unknown_outcome";
        /** AICallSummary */
        AICallSummary: {
            /** Actual Model */
            actual_model: string | null;
            /** Actual Provider */
            actual_provider: string | null;
            /** Attempt Number */
            attempt_number: number;
            /** Completed At */
            completed_at: string | null;
            /** Finish Reason */
            finish_reason: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latency Ms */
            latency_ms: number | null;
            /** Requested Model */
            requested_model: string;
            /** Requested Provider */
            requested_provider: string | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["AICallStatus"];
            /** Turn Number */
            turn_number: number;
            usage: components["schemas"]["TokenUsage"];
        };
        /** ArticleModelUsage */
        ArticleModelUsage: {
            /** Attempt Count */
            attempt_count: number;
            /** Model */
            model: string | null;
            /** Provider */
            provider: string | null;
        };
        /** ArticlePage */
        ArticlePage: {
            /** Items */
            items: components["schemas"]["ArticleSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** ArticlePageResponse */
        ArticlePageResponse: {
            page: components["schemas"]["ArticlePage"];
        };
        /** ArticleSummary */
        ArticleSummary: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Artifact Media Type */
            artifact_media_type: string;
            /** Artifact Path */
            artifact_path: string;
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /**
             * Completed At
             * Format: date-time
             */
            completed_at: string;
            /** Evaluation Workspace Id */
            evaluation_workspace_id: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            kind: components["schemas"]["GenerationKind"];
            /** Request Text */
            request_text: string;
            /** Requested Primary Model */
            requested_primary_model: string;
            /** Rerun Of Generation Id */
            rerun_of_generation_id: string | null;
            /** Season Year */
            season_year: number;
            /** Submitted Version Content Hash */
            submitted_version_content_hash: string;
            /**
             * Submitted Version Id
             * Format: uuid
             */
            submitted_version_id: string;
            /** Submitted Version Revision */
            submitted_version_revision: number;
            /** Title */
            title: string;
            usage: components["schemas"]["ArticleUsageSummary"];
            /** Week End */
            week_end: number | null;
            /** Week Start */
            week_start: number | null;
            /** Workspace Sequence Number */
            workspace_sequence_number: number | null;
        };
        /** ArticleUsageSummary */
        ArticleUsageSummary: {
            /** Attempt Count */
            attempt_count: number;
            /** Complete */
            complete: boolean;
            /** Currency */
            currency: string;
            /** Estimated Cost */
            estimated_cost: string | null;
            /** Models */
            models: components["schemas"]["ArticleModelUsage"][];
            /**
             * Quoted At
             * Format: date-time
             */
            quoted_at: string;
            /** Total Tokens */
            total_tokens: number;
        };
        /** Artifact */
        Artifact: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Finalized At */
            finalized_at: string | null;
            /** Finalized Version Id */
            finalized_version_id: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Media Type */
            media_type: string;
            /** Path */
            path: string;
        };
        /** ArtifactPage */
        ArtifactPage: {
            /** Items */
            items: components["schemas"]["ArtifactSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** ArtifactPageResponse */
        ArtifactPageResponse: {
            page: components["schemas"]["ArtifactPage"];
        };
        /** ArtifactResponse */
        ArtifactResponse: {
            artifact: components["schemas"]["Artifact"];
        };
        /** ArtifactSummary */
        ArtifactSummary: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Finalized At */
            finalized_at: string | null;
            /** Finalized Version Id */
            finalized_version_id: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latest Version At */
            latest_version_at: string | null;
            /** Media Type */
            media_type: string;
            /** Path */
            path: string;
            /** Revision Count */
            revision_count: number;
        };
        /** ArtifactVersion */
        ArtifactVersion: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Content */
            content: string;
            /** Content Hash */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision Number */
            revision_number: number;
            /** Source Ai Call Id */
            source_ai_call_id: string | null;
            /** Source Tool Call Id */
            source_tool_call_id: string | null;
        };
        /** ArtifactVersionPage */
        ArtifactVersionPage: {
            /** Items */
            items: components["schemas"]["ArtifactVersionSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** ArtifactVersionPageResponse */
        ArtifactVersionPageResponse: {
            page: components["schemas"]["ArtifactVersionPage"];
        };
        /** ArtifactVersionResponse */
        ArtifactVersionResponse: {
            version: components["schemas"]["ArtifactVersion"];
        };
        /** ArtifactVersionSummary */
        ArtifactVersionSummary: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Content Hash */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision Number */
            revision_number: number;
            /** Source Ai Call Id */
            source_ai_call_id: string | null;
            /** Source Tool Call Id */
            source_tool_call_id: string | null;
        };
        backend__services__datalayer__canonical_json__JsonValue: boolean | number | string | components["schemas"]["backend__services__datalayer__canonical_json__JsonValue"][] | {
            [key: string]: components["schemas"]["backend__services__datalayer__canonical_json__JsonValue"];
        } | null;
        /** BudgetTradeAsset */
        BudgetTradeAsset: {
            /** Amount */
            amount: number;
            direction: components["schemas"]["TradeAssetDirection"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "budget";
        };
        /**
         * CanonicalRevision
         * @description One immutable competition-wide canonical memory state.
         */
        CanonicalRevision: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /** Competition Season Id */
            competition_season_id?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Knowledge Cutoff At */
            knowledge_cutoff_at?: string | null;
            /** Previous Revision Id */
            previous_revision_id?: string | null;
            /** Producing Generation Id */
            producing_generation_id?: string | null;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Sequence Number */
            sequence_number: number;
            /** State Content Hash */
            state_content_hash: string;
            /** Week */
            week?: number | null;
        };
        /** Competition */
        Competition: {
            /** Archived At */
            archived_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Display Name */
            display_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** CompetitionActivitySummary */
        CompetitionActivitySummary: {
            /** Latest Ready Snapshot At */
            latest_ready_snapshot_at: string | null;
            latest_season: components["schemas"]["CompetitionSeason"] | null;
            /** Latest Submitted Article At */
            latest_submitted_article_at: string | null;
            /** Latest Successful Refresh At */
            latest_successful_refresh_at: string | null;
            latest_terminal_refresh: components["schemas"]["LatestRefreshSummary"] | null;
            /** Season Count */
            season_count: number;
        };
        /** CompetitionContextNoteIdentity */
        CompetitionContextNoteIdentity: {
            /** Note Key */
            note_key: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            scope: "competition";
        };
        /** CompetitionOverview */
        CompetitionOverview: {
            competition: components["schemas"]["Competition"];
            summary: components["schemas"]["CompetitionActivitySummary"];
        };
        /** CompetitionOverviewPage */
        CompetitionOverviewPage: {
            /** Items */
            items: components["schemas"]["CompetitionOverview"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** CompetitionOverviewResponse */
        CompetitionOverviewResponse: {
            competition: components["schemas"]["Competition"];
            summary: components["schemas"]["CompetitionActivitySummary"];
        };
        /** CompetitionPageResponse */
        CompetitionPageResponse: {
            page: components["schemas"]["CompetitionOverviewPage"];
        };
        /** CompetitionResponse */
        CompetitionResponse: {
            competition: components["schemas"]["Competition"];
        };
        /** CompetitionSeason */
        CompetitionSeason: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Season Year */
            season_year: number;
            /** Sequence Number */
            sequence_number: number;
            /** Sleeper League Id */
            sleeper_league_id: string;
        };
        /** CompetitionSeasonActivitySummary */
        CompetitionSeasonActivitySummary: {
            /** Latest Ready Snapshot At */
            latest_ready_snapshot_at: string | null;
            /** Latest Successful Refresh At */
            latest_successful_refresh_at: string | null;
            latest_terminal_refresh: components["schemas"]["LatestRefreshSummary"] | null;
            /** League Name */
            league_name: string | null;
            /** League Status */
            league_status: string | null;
        };
        /** CompetitionSeasonContextNoteIdentity */
        CompetitionSeasonContextNoteIdentity: {
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** Note Key */
            note_key: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            scope: "competition_season";
        };
        /** CompetitionSeasonDetailResponse */
        CompetitionSeasonDetailResponse: {
            normalized_overview: components["schemas"]["LeagueSeasonOverview"] | null;
            season: components["schemas"]["CompetitionSeason"];
            summary: components["schemas"]["CompetitionSeasonActivitySummary"];
        };
        /** CompetitionSeasonOverview */
        CompetitionSeasonOverview: {
            season: components["schemas"]["CompetitionSeason"];
            summary: components["schemas"]["CompetitionSeasonActivitySummary"];
        };
        /** CompetitionSeasonOverviewPage */
        CompetitionSeasonOverviewPage: {
            /** Items */
            items: components["schemas"]["CompetitionSeasonOverview"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** CompetitionSeasonPageResponse */
        CompetitionSeasonPageResponse: {
            page: components["schemas"]["CompetitionSeasonOverviewPage"];
        };
        /** CompetitionSeasonResponse */
        CompetitionSeasonResponse: {
            season: components["schemas"]["CompetitionSeason"];
        };
        /**
         * CompletenessWarning
         * @description Safe structured warning retained with a snapshot or workflow result.
         */
        CompletenessWarning: {
            /** Code */
            code: string;
            scope_key?: components["schemas"]["ScopeKey"] | null;
            /** Summary */
            summary: string;
        };
        /** ContextNote */
        ContextNote: {
            content: components["schemas"]["ContextNoteContent"];
            item: components["schemas"]["MemoryItemIdentity"];
            /** Note Identity */
            note_identity: components["schemas"]["CompetitionContextNoteIdentity"] | components["schemas"]["CompetitionSeasonContextNoteIdentity"] | components["schemas"]["FranchiseContextNoteIdentity"];
            version: components["schemas"]["MemoryVersionMetadata"];
        };
        /** ContextNoteContent */
        ContextNoteContent: {
            /** Narrative */
            narrative: string;
            /** Outlook */
            outlook?: string | null;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["ContextNoteStatus"];
            /** Tags */
            tags: string[];
        };
        /** ContextNoteCreateRequest */
        ContextNoteCreateRequest: {
            content: components["schemas"]["ContextNoteContent"];
            /** Identity */
            identity: components["schemas"]["CompetitionContextNoteIdentity"] | components["schemas"]["CompetitionSeasonContextNoteIdentity"] | components["schemas"]["FranchiseContextNoteIdentity"];
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** ContextNoteHistoryResponse */
        ContextNoteHistoryResponse: {
            /** Items */
            items: components["schemas"]["ContextNote"][];
        };
        /** ContextNoteReplaceRequest */
        ContextNoteReplaceRequest: {
            content: components["schemas"]["ContextNoteContent"];
            /** Expected Item Revision */
            expected_item_revision: number;
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** ContextNoteResponse */
        ContextNoteResponse: {
            memory: components["schemas"]["ContextNote"];
        };
        /**
         * ContextNoteStatus
         * @enum {string}
         */
        ContextNoteStatus: "active" | "archived";
        /** CoreErrorDetail */
        CoreErrorDetail: {
            /**
             * Code
             * @enum {string}
             */
            code: "competition_not_found" | "competition_season_not_found" | "competition_archived" | "competition_season_year_exists" | "sleeper_league_id_exists" | "competition_concurrency_conflict" | "roster_mapping_conflict" | "roster_mapping_source_stale";
            /** Correlation Id */
            correlation_id?: string | null;
            /** Field Errors */
            field_errors?: {
                [key: string]: string[];
            } | null;
            /** Summary */
            summary: string;
        };
        /** CoreErrorResponse */
        CoreErrorResponse: {
            error: components["schemas"]["CoreErrorDetail"];
        };
        /**
         * CreateCompetitionBody
         * @example {
         *       "display_name": "The League"
         *     }
         */
        CreateCompetitionBody: {
            /** Display Name */
            display_name: string;
        };
        /**
         * CreateCompetitionSeasonBody
         * @example {
         *       "season_year": 2026,
         *       "sleeper_league_id": "1234567890"
         *     }
         */
        CreateCompetitionSeasonBody: {
            /** Season Year */
            season_year: number;
            /** Sleeper League Id */
            sleeper_league_id: string;
        };
        /** CreateFranchiseTargetBody */
        CreateFranchiseTargetBody: {
            /** Display Name */
            display_name: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "new";
        };
        /** DataErrorDetail */
        DataErrorDetail: {
            /**
             * Code
             * @enum {string}
             */
            code: "invalid_data_request" | "data_resource_not_found" | "data_scope_conflict" | "endpoint_payload_rejected" | "snapshot_unavailable" | "datalayer_internal_failure";
            /** Correlation Id */
            correlation_id?: string | null;
            /** Summary */
            summary: string;
        };
        /** DataErrorResponse */
        DataErrorResponse: {
            error: components["schemas"]["DataErrorDetail"];
        };
        /** DataSnapshotPageResponse */
        DataSnapshotPageResponse: {
            page: components["schemas"]["DataSnapshotSummaryPage"];
        };
        /** DataSnapshotSummary */
        DataSnapshotSummary: {
            artifact: components["schemas"]["SnapshotArtifactSummary"] | null;
            /**
             * As Of Date
             * Format: date
             */
            as_of_date: string;
            /** Build Key */
            build_key: string;
            /** Code Version */
            code_version: string;
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /** Completed At */
            completed_at: string | null;
            /** Completeness Warnings */
            completeness_warnings: components["schemas"]["CompletenessWarning"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            failure: components["schemas"]["SnapshotFailure"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Primary Competition Season Id
             * Format: uuid
             */
            primary_competition_season_id: string;
            /** Snapshot Projection Version */
            snapshot_projection_version: string;
            status: components["schemas"]["SnapshotStatus"];
            /** Through Week */
            through_week: number;
        };
        /** DataSnapshotSummaryPage */
        DataSnapshotSummaryPage: {
            /** Items */
            items: components["schemas"]["DataSnapshotSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** DraftPickTradeAsset */
        DraftPickTradeAsset: {
            direction: components["schemas"]["TradeAssetDirection"];
            /**
             * Draft Pick Id
             * Format: uuid
             */
            draft_pick_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "draft_pick";
        };
        /**
         * EndpointKind
         * @enum {string}
         */
        EndpointKind: "league" | "league_users" | "league_rosters" | "nfl_state" | "player_catalog" | "matchups" | "transactions" | "traded_picks" | "winners_bracket" | "losers_bracket";
        /** EventContent */
        "EventContent-Input": {
            confidence: components["schemas"]["ReceiptConfidence"];
            /** Details */
            details: components["schemas"]["TradeEventPayload"] | components["schemas"]["MatchupEventPayload"];
            event_type: components["schemas"]["EventType"];
            /** Headline */
            headline: string;
            /** Primary Api Request Id */
            primary_api_request_id?: string | null;
            /** Primary Tool Call Id */
            primary_tool_call_id?: string | null;
            /** Salience */
            salience: number;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Source Hints */
            source_hints?: {
                [key: string]: components["schemas"]["JsonValue-Input"];
            } | null;
            status: components["schemas"]["EventStatus"];
            /** Summary */
            summary: string;
        };
        /** EventContent */
        "EventContent-Output": {
            confidence: components["schemas"]["ReceiptConfidence"];
            /** Details */
            details: components["schemas"]["TradeEventPayload"] | components["schemas"]["MatchupEventPayload"];
            event_type: components["schemas"]["EventType"];
            /** Headline */
            headline: string;
            /** Primary Api Request Id */
            primary_api_request_id?: string | null;
            /** Primary Tool Call Id */
            primary_tool_call_id?: string | null;
            /** Salience */
            salience: number;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Source Hints */
            source_hints?: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            status: components["schemas"]["EventStatus"];
            /** Summary */
            summary: string;
        };
        /** EventCreateRequest */
        EventCreateRequest: {
            content: components["schemas"]["EventContent-Input"];
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** EventEvidenceRef */
        EventEvidenceRef: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "event";
            role: components["schemas"]["EvidenceRole"];
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** EventHistoryResponse */
        EventHistoryResponse: {
            /** Items */
            items: components["schemas"]["VersionedMemory_EventContent_"][];
        };
        /** EventReplaceRequest */
        EventReplaceRequest: {
            content: components["schemas"]["EventContent-Input"];
            /** Expected Item Revision */
            expected_item_revision: number;
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** EventResponse */
        EventResponse: {
            memory: components["schemas"]["VersionedMemory_EventContent_"];
        };
        /**
         * EventStatus
         * @enum {string}
         */
        EventStatus: "active" | "superseded" | "rejected" | "archived";
        /**
         * EventType
         * @enum {string}
         */
        EventType: "trade" | "matchup";
        /**
         * EvidenceRole
         * @enum {string}
         */
        EvidenceRole: "origin" | "support" | "update" | "payoff";
        /** ExistingFranchiseTargetBody */
        ExistingFranchiseTargetBody: {
            /**
             * Franchise Id
             * Format: uuid
             */
            franchise_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "existing";
        };
        /** FactContent */
        "FactContent-Input": {
            /** Category */
            category: string;
            /** Claim */
            claim: string;
            confidence: components["schemas"]["ReceiptConfidence"];
            /** Numbers */
            numbers: {
                [key: string]: components["schemas"]["JsonValue-Input"];
            };
            /** Originating Event Version Ids */
            originating_event_version_ids: string[];
            /** Primary Api Request Id */
            primary_api_request_id?: string | null;
            /** Primary Tool Call Id */
            primary_tool_call_id?: string | null;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Source Hints */
            source_hints?: {
                [key: string]: components["schemas"]["JsonValue-Input"];
            } | null;
            status: components["schemas"]["FactStatus"];
            /** Subjects */
            subjects: (components["schemas"]["FranchiseRef_FactSubjectRole_"] | components["schemas"]["PlayerRef_FactSubjectRole_"] | components["schemas"]["SeasonRosterRef_FactSubjectRole_"] | components["schemas"]["SeasonRef_FactSubjectRole_"] | components["schemas"]["SleeperUserRef_FactSubjectRole_"])[];
        };
        /** FactContent */
        "FactContent-Output": {
            /** Category */
            category: string;
            /** Claim */
            claim: string;
            confidence: components["schemas"]["ReceiptConfidence"];
            /** Numbers */
            numbers: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            };
            /** Originating Event Version Ids */
            originating_event_version_ids: string[];
            /** Primary Api Request Id */
            primary_api_request_id?: string | null;
            /** Primary Tool Call Id */
            primary_tool_call_id?: string | null;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            /** Source Hints */
            source_hints?: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            status: components["schemas"]["FactStatus"];
            /** Subjects */
            subjects: (components["schemas"]["FranchiseRef_FactSubjectRole_"] | components["schemas"]["PlayerRef_FactSubjectRole_"] | components["schemas"]["SeasonRosterRef_FactSubjectRole_"] | components["schemas"]["SeasonRef_FactSubjectRole_"] | components["schemas"]["SleeperUserRef_FactSubjectRole_"])[];
        };
        /** FactCreateRequest */
        FactCreateRequest: {
            content: components["schemas"]["FactContent-Input"];
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** FactEvidenceRef */
        FactEvidenceRef: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "fact";
            role: components["schemas"]["EvidenceRole"];
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** FactHistoryResponse */
        FactHistoryResponse: {
            /** Items */
            items: components["schemas"]["VersionedMemory_FactContent_"][];
        };
        /** FactOriginatingEventExpansion */
        FactOriginatingEventExpansion: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "fact_originating_event";
            memory: components["schemas"]["VersionedMemory_EventContent_"];
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** FactReplaceRequest */
        FactReplaceRequest: {
            content: components["schemas"]["FactContent-Input"];
            /** Expected Item Revision */
            expected_item_revision: number;
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** FactResponse */
        FactResponse: {
            memory: components["schemas"]["VersionedMemory_FactContent_"];
        };
        /**
         * FactStatus
         * @enum {string}
         */
        FactStatus: "active" | "superseded" | "rejected" | "archived";
        /**
         * FactSubjectRole
         * @enum {string}
         */
        FactSubjectRole: "subject";
        /**
         * FirePolicy
         * @enum {string}
         */
        FirePolicy: "one_shot" | "recurring" | "until_resolved";
        /** FranchiseContextNoteIdentity */
        FranchiseContextNoteIdentity: {
            /**
             * Franchise Id
             * Format: uuid
             */
            franchise_id: string;
            /** Note Key */
            note_key: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            scope: "franchise";
        };
        /** FranchiseIdentity */
        FranchiseIdentity: {
            /** Archived At */
            archived_at: string | null;
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /** Display Name */
            display_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** FranchiseRef[FactSubjectRole] */
        FranchiseRef_FactSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "franchise";
            role: components["schemas"]["FactSubjectRole"];
        };
        /** FranchiseRef[StorylineSubjectRole] */
        FranchiseRef_StorylineSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "franchise";
            role: components["schemas"]["StorylineSubjectRole"];
        };
        /** Generation */
        Generation: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Current Stage */
            current_stage: string | null;
            /** Current Turn */
            current_turn: number;
            /** Data Snapshot Id */
            data_snapshot_id: string | null;
            /** Domain Cutoff At */
            domain_cutoff_at: string | null;
            /** Domain Cutoff Week */
            domain_cutoff_week: number | null;
            /** Evaluation Workspace Id */
            evaluation_workspace_id: string | null;
            /** Failure Category */
            failure_category: string | null;
            /** Failure Summary */
            failure_summary: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Manifest */
            input_manifest: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Input Memory Artifact Generation Id */
            input_memory_artifact_generation_id: string | null;
            /** Input Memory Artifact Version Id */
            input_memory_artifact_version_id: string | null;
            /** Input Memory Revision Id */
            input_memory_revision_id: string | null;
            kind: components["schemas"]["GenerationKind"];
            /** Knowledge Cutoff At */
            knowledge_cutoff_at: string | null;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Manifest Schema Version */
            manifest_schema_version: number | null;
            /** Progress Updated At */
            progress_updated_at: string | null;
            /** Request Text */
            request_text: string;
            /** Requested Primary Model */
            requested_primary_model: string;
            /** Rerun Of Generation Id */
            rerun_of_generation_id: string | null;
            /** Settings */
            settings: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            };
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["GenerationStatus"];
            /** Submitted Artifact Version Id */
            submitted_artifact_version_id: string | null;
            /** Week End */
            week_end: number | null;
            /** Week Start */
            week_start: number | null;
            /** Workspace Sequence Number */
            workspace_sequence_number: number | null;
        };
        /** GenerationBiasSettings */
        GenerationBiasSettings: {
            /**
             * Disfavored Teams
             * @default []
             */
            disfavored_teams: string[];
            /**
             * Favored Teams
             * @default []
             */
            favored_teams: string[];
            /**
             * Intensity
             * @default 1
             */
            intensity: number;
        };
        /**
         * GenerationDetail
         * @description Complete generation row without child-resource payloads.
         */
        GenerationDetail: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Current Stage */
            current_stage: string | null;
            /** Current Turn */
            current_turn: number;
            /** Data Snapshot Id */
            data_snapshot_id: string | null;
            /** Domain Cutoff At */
            domain_cutoff_at: string | null;
            /** Domain Cutoff Week */
            domain_cutoff_week: number | null;
            /** Evaluation Workspace Id */
            evaluation_workspace_id: string | null;
            /** Failure Category */
            failure_category: string | null;
            /** Failure Summary */
            failure_summary: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Manifest */
            input_manifest: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Input Memory Artifact Generation Id */
            input_memory_artifact_generation_id: string | null;
            /** Input Memory Artifact Version Id */
            input_memory_artifact_version_id: string | null;
            /** Input Memory Revision Id */
            input_memory_revision_id: string | null;
            kind: components["schemas"]["GenerationKind"];
            /** Knowledge Cutoff At */
            knowledge_cutoff_at: string | null;
            /** Manifest Hash */
            manifest_hash: string | null;
            /** Manifest Schema Version */
            manifest_schema_version: number | null;
            /** Progress Updated At */
            progress_updated_at: string | null;
            /** Request Text */
            request_text: string;
            /** Requested Primary Model */
            requested_primary_model: string;
            /** Rerun Of Generation Id */
            rerun_of_generation_id: string | null;
            /** Settings */
            settings: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            };
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["GenerationStatus"];
            /** Submitted Artifact Version Id */
            submitted_artifact_version_id: string | null;
            /** Week End */
            week_end: number | null;
            /** Week Start */
            week_start: number | null;
            /** Workspace Sequence Number */
            workspace_sequence_number: number | null;
        };
        /** GenerationDetailResponse */
        GenerationDetailResponse: {
            generation: components["schemas"]["GenerationDetail"];
        };
        /**
         * GenerationKind
         * @enum {string}
         */
        GenerationKind: "live" | "backtest";
        /** GenerationModelSettings */
        GenerationModelSettings: {
            /**
             * Fallback Models
             * @default []
             */
            fallback_models: string[];
            retry?: components["schemas"]["GenerationRetrySettings"];
        };
        /** GenerationPage */
        GenerationPage: {
            /** Items */
            items: components["schemas"]["GenerationSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** GenerationPageResponse */
        GenerationPageResponse: {
            page: components["schemas"]["GenerationPage"];
        };
        /** GenerationReportSettings */
        GenerationReportSettings: {
            /**
             * Avoid Topics
             * @default []
             */
            avoid_topics: string[];
            bias?: components["schemas"]["GenerationBiasSettings"] | null;
            /**
             * Evidence Policy
             * @default standard
             * @enum {string}
             */
            evidence_policy: "strict" | "standard" | "relaxed";
            /**
             * Focus Hints
             * @default []
             */
            focus_hints: string[];
            /**
             * Focus Teams
             * @default []
             */
            focus_teams: string[];
            /**
             * Length Target
             * @default 1000
             */
            length_target: number;
            /**
             * Profanity Policy
             * @default none
             * @enum {string}
             */
            profanity_policy: "none" | "mild" | "unrestricted";
            tone?: components["schemas"]["GenerationToneSettings"];
            /**
             * Voice
             * @default sports columnist
             */
            voice: string;
        };
        /** GenerationResponse */
        GenerationResponse: {
            generation: components["schemas"]["Generation"];
        };
        /** GenerationRetrySettings */
        GenerationRetrySettings: {
            /**
             * Base Delay Seconds
             * @default 1
             */
            base_delay_seconds: number;
            /**
             * Max Delay Seconds
             * @default 30
             */
            max_delay_seconds: number;
            /**
             * Max Retries
             * @default 3
             */
            max_retries: number;
        };
        /** GenerationRunnerSettings */
        GenerationRunnerSettings: {
            /**
             * Max Turns
             * @default 60
             */
            max_turns: number;
            /**
             * Procedure History Mode
             * @default replace
             * @enum {string}
             */
            procedure_history_mode: "replace" | "append";
        };
        /** GenerationSettings */
        GenerationSettings: {
            model?: components["schemas"]["GenerationModelSettings"];
            report?: components["schemas"]["GenerationReportSettings"];
            runner?: components["schemas"]["GenerationRunnerSettings"];
        };
        /**
         * GenerationStatus
         * @enum {string}
         */
        GenerationStatus: "pending" | "running" | "succeeded" | "failed" | "cancelled";
        /** GenerationSummary */
        GenerationSummary: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Current Stage */
            current_stage: string | null;
            /** Current Turn */
            current_turn: number;
            /** Evaluation Workspace Id */
            evaluation_workspace_id: string | null;
            /** Failure Category */
            failure_category: string | null;
            /** Failure Summary */
            failure_summary: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            kind: components["schemas"]["GenerationKind"];
            /** Progress Updated At */
            progress_updated_at: string | null;
            /** Request Text */
            request_text: string;
            /** Requested Primary Model */
            requested_primary_model: string;
            /** Rerun Of Generation Id */
            rerun_of_generation_id: string | null;
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["GenerationStatus"];
            /** Submitted Artifact Version Id */
            submitted_artifact_version_id: string | null;
            /** Week End */
            week_end: number | null;
            /** Week Start */
            week_start: number | null;
            /** Workspace Sequence Number */
            workspace_sequence_number: number | null;
        };
        /** GenerationToneSettings */
        GenerationToneSettings: {
            /**
             * Hype Level
             * @default 1
             */
            hype_level: number;
            /**
             * Seriousness
             * @default 1
             */
            seriousness: number;
            /**
             * Snark Level
             * @default 1
             */
            snark_level: number;
        };
        /** GenerationUsage */
        GenerationUsage: {
            /** Attempt Count */
            attempt_count: number;
            /** Breakdowns */
            breakdowns: components["schemas"]["ModelUsageBreakdown"][];
            /** Complete */
            complete: boolean;
            /** Currency */
            currency: string;
            /** Estimated Cost */
            estimated_cost: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Latency Ms */
            latency_ms: number;
            /** Missing Usage Call Ids */
            missing_usage_call_ids: string[];
            /**
             * Quoted At
             * Format: date-time
             */
            quoted_at: string;
            tokens: components["schemas"]["TokenTotals"];
            /** Unpriced Call Ids */
            unpriced_call_ids: string[];
        };
        /** GenerationUsageResponse */
        GenerationUsageResponse: {
            usage: components["schemas"]["GenerationUsage"];
        };
        /** HealthResponse */
        HealthResponse: {
            /**
             * Status
             * @enum {string}
             */
            status: "alive" | "ready";
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HydratedMemoryMatch */
        HydratedMemoryMatch: {
            /**
             * Exact References
             * @default []
             */
            exact_references: (components["schemas"]["StorylineEvidenceExpansion"] | components["schemas"]["FactOriginatingEventExpansion"])[];
            /** Match Reasons */
            match_reasons: components["schemas"]["SearchMatchReason"][];
            /**
             * Matched Entity Keys
             * @default []
             */
            matched_entity_keys: string[];
            /**
             * Matched Evidence Version Ids
             * @default []
             */
            matched_evidence_version_ids: string[];
            /**
             * Matched Related Item Ids
             * @default []
             */
            matched_related_item_ids: string[];
            /**
             * Matched Tags
             * @default []
             */
            matched_tags: string[];
            /** Memory */
            memory: components["schemas"]["VersionedMemory_FactContent_"] | components["schemas"]["VersionedMemory_EventContent_"] | components["schemas"]["VersionedMemory_StorylineContent_"] | components["schemas"]["VersionedMemory_TriggerContent_"] | components["schemas"]["ContextNote"];
            /** Score */
            score: number;
            score_components: components["schemas"]["SearchScoreComponents"];
            /**
             * Stable References
             * @default []
             */
            stable_references: (components["schemas"]["RelatedStorylineExpansion"] | components["schemas"]["TriggerTargetStorylineExpansion"] | components["schemas"]["TriggerOriginEventExpansion"])[];
        };
        "JsonValue-Input": unknown;
        /** LatestRefreshSummary */
        LatestRefreshSummary: {
            /**
             * Completed At
             * Format: date-time
             */
            completed_at: string;
            /** Failed Request Count */
            failed_request_count: number;
            /** Request Count */
            request_count: number;
            /** Requested Through Week */
            requested_through_week: number | null;
            status: components["schemas"]["RefreshStatus"];
            /** Succeeded Request Count */
            succeeded_request_count: number;
        };
        /** LeagueSeasonOverview */
        LeagueSeasonOverview: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /** Competition Name */
            competition_name: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** League Average Match */
            league_average_match: number | null;
            /** League Name */
            league_name: string;
            /** Playoff Start Week */
            playoff_start_week: number | null;
            /** Playoff Team Count */
            playoff_team_count: number | null;
            /** Provider Settings */
            provider_settings: {
                [key: string]: components["schemas"]["backend__services__datalayer__canonical_json__JsonValue"];
            };
            /** Roster Count */
            roster_count: number;
            /** Roster Positions */
            roster_positions: string[];
            /** Scoring Settings */
            scoring_settings: {
                [key: string]: components["schemas"]["backend__services__datalayer__canonical_json__JsonValue"];
            };
            /** Season Year */
            season_year: number;
            /** Sequence Number */
            sequence_number: number;
            /** Sleeper League Id */
            sleeper_league_id: string;
            /**
             * Source Api Request Id
             * Format: uuid
             */
            source_api_request_id: string;
            /** Status */
            status: string | null;
        };
        /** LeagueSeasonOverviewResponse */
        LeagueSeasonOverviewResponse: {
            overview: components["schemas"]["LeagueSeasonOverview"];
        };
        /**
         * ManualRefreshBody
         * @example {}
         * @example {
         *       "through_week": 8
         *     }
         */
        ManualRefreshBody: {
            /** Through Week */
            through_week?: number | null;
        };
        /** ManualRefreshResponse */
        ManualRefreshResponse: {
            /** Effective Through Week */
            effective_through_week: number | null;
            refresh: components["schemas"]["RefreshRun"];
            /** Scope Results */
            scope_results: components["schemas"]["ScopeRefreshResult"][];
        };
        /** MatchupEventPayload */
        MatchupEventPayload: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "matchup";
            /**
             * Loser Franchise Id
             * Format: uuid
             */
            loser_franchise_id: string;
            /** Sleeper Matchup Id */
            sleeper_matchup_id: string;
            /**
             * Winner Franchise Id
             * Format: uuid
             */
            winner_franchise_id: string;
        };
        /** MemoryErrorDetail */
        MemoryErrorDetail: {
            /**
             * Code
             * @enum {string}
             */
            code: "canonical_state_inconsistent" | "context_note_conflict" | "cross_competition_entity" | "cross_competition_reference" | "generation_memory_closed" | "memory_identity_conflict" | "revision_not_found" | "search_projection_inconsistent" | "stale_canonical_revision" | "stale_item_version" | "target_not_found" | "wrong_target_kind";
            /** Message */
            message: string;
        };
        /** MemoryErrorResponse */
        MemoryErrorResponse: {
            detail: components["schemas"]["MemoryErrorDetail"];
        };
        /** MemoryItemIdentity */
        MemoryItemIdentity: {
            /** Agent Key */
            agent_key?: string | null;
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            kind: components["schemas"]["MemoryKind"];
        };
        /**
         * MemoryKind
         * @enum {string}
         */
        MemoryKind: "storyline" | "fact" | "event" | "trigger" | "context_note";
        /**
         * MemoryMutationMetadata
         * @description Version-envelope values supplied with one complete proposal.
         */
        MemoryMutationMetadata: {
            /** Agent Key */
            agent_key?: string | null;
            /** Change Reason */
            change_reason?: string | null;
            /** Competition Season Id */
            competition_season_id?: string | null;
            /** Creating Tool Call Id */
            creating_tool_call_id?: string | null;
            /** Occurred At */
            occurred_at?: string | null;
            /** Week */
            week?: number | null;
        };
        /**
         * MemoryMutationOrigin
         * @description Canonical parent and reporting provenance for a public mutation.
         */
        MemoryMutationOrigin: {
            /** Competition Season Id */
            competition_season_id?: string | null;
            /**
             * Expected Revision Id
             * Format: uuid
             */
            expected_revision_id: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Knowledge Cutoff At */
            knowledge_cutoff_at?: string | null;
            /** Week */
            week?: number | null;
        };
        /** MemoryMutationResponse */
        MemoryMutationResponse: {
            result: components["schemas"]["MemoryMutationResult"];
        };
        /**
         * MemoryMutationResult
         * @description Committed revision and the canonical identities introduced within it.
         */
        MemoryMutationResult: {
            /** Changes */
            changes: components["schemas"]["ProposedMemoryRef"][];
            revision: components["schemas"]["CanonicalRevision"] | null;
        };
        /** MemoryRetrievalResult */
        MemoryRetrievalResult: {
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /** Matches */
            matches: components["schemas"]["HydratedMemoryMatch"][];
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** MemorySearchRequest */
        MemorySearchRequest: {
            /**
             * Expand Exact References
             * @default false
             */
            expand_exact_references: boolean;
            /**
             * Expand Stable References
             * @default false
             */
            expand_stable_references: boolean;
            query: components["schemas"]["SearchDocumentQuery"];
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** MemorySearchResponse */
        MemorySearchResponse: {
            result: components["schemas"]["MemoryRetrievalResult"];
        };
        /** MemoryVersionMetadata */
        MemoryVersionMetadata: {
            /** Change Reason */
            change_reason?: string | null;
            /** Competition Season Id */
            competition_season_id?: string | null;
            /** Content Schema Version */
            content_schema_version: number;
            /**
             * Creating Generation Id
             * Format: uuid
             */
            creating_generation_id: string;
            /** Creating Tool Call Id */
            creating_tool_call_id?: string | null;
            /**
             * Introduced Revision Id
             * Format: uuid
             */
            introduced_revision_id: string;
            /** Occurred At */
            occurred_at?: string | null;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Retired Revision Id */
            retired_revision_id?: string | null;
            /** Revision Number */
            revision_number: number;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
            /** Week */
            week?: number | null;
        };
        /** ModelCatalogItem */
        ModelCatalogItem: {
            /** Display Name */
            display_name: string;
            /** Is Default */
            is_default: boolean;
            /** Model */
            model: string;
            /** Provider */
            provider: string | null;
            /** Supports Reasoning */
            supports_reasoning: boolean;
        };
        /** ModelCatalogResponse */
        ModelCatalogResponse: {
            /** Models */
            models: components["schemas"]["ModelCatalogItem"][];
        };
        /** ModelUsageBreakdown */
        ModelUsageBreakdown: {
            /** Attempt Count */
            attempt_count: number;
            /** Complete */
            complete: boolean;
            /** Currency */
            currency: string;
            /** Estimated Cost */
            estimated_cost: string | null;
            /** Latency Ms */
            latency_ms: number;
            /** Model */
            model: string | null;
            /** Provider */
            provider: string | null;
            tokens: components["schemas"]["TokenTotals"];
        };
        /**
         * NormalizationStatus
         * @enum {string}
         */
        NormalizationStatus: "pending" | "succeeded" | "rejected" | "not_applicable";
        /** ObservedRosterMapping */
        ObservedRosterMapping: {
            /** Franchise Id */
            franchise_id?: string | null;
            /** Franchise Name */
            franchise_name?: string | null;
            /** Managers */
            managers: components["schemas"]["RosterManagerEvidence"][];
            /** Sleeper Roster Id */
            sleeper_roster_id: string;
            /** Suggested Display Name */
            suggested_display_name: string;
        };
        /**
         * PatchCompetitionBody
         * @example {
         *       "display_name": "Renamed League"
         *     }
         * @example {
         *       "archived": true
         *     }
         */
        PatchCompetitionBody: {
            /** Archived */
            archived?: true | null;
            /** Display Name */
            display_name?: string | null;
        };
        /** PlannedEndpointScope */
        PlannedEndpointScope: {
            /**
             * Dependency Scope Keys
             * @default []
             */
            dependency_scope_keys: components["schemas"]["ScopeKey"][];
            endpoint_kind: components["schemas"]["EndpointKind"];
            /**
             * Required
             * @default true
             */
            required: boolean;
            scope_key: components["schemas"]["ScopeKey"];
        };
        /** PlayerRef[FactSubjectRole] */
        PlayerRef_FactSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /** Id */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "player";
            role: components["schemas"]["FactSubjectRole"];
        };
        /** PlayerRef[StorylineSubjectRole] */
        PlayerRef_StorylineSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /** Id */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "player";
            role: components["schemas"]["StorylineSubjectRole"];
        };
        /** PlayerTradeAsset */
        PlayerTradeAsset: {
            direction: components["schemas"]["TradeAssetDirection"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "player";
            /** Player Id */
            player_id: string;
        };
        /**
         * ProposedMemoryRef
         * @description Preallocated canonical identity returned to a proposal caller.
         */
        ProposedMemoryRef: {
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            kind: components["schemas"]["MemoryKind"];
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * PutRosterMappingsBody
         * @example {
         *       "assignments": [
         *         {
         *           "sleeper_roster_id": "1",
         *           "target": {
         *             "franchise_id": "e9c48ec7-95fe-44ed-85d6-d658f7022bd2",
         *             "kind": "existing"
         *           }
         *         },
         *         {
         *           "sleeper_roster_id": "2",
         *           "target": {
         *             "display_name": "Expansion Team",
         *             "kind": "new"
         *           }
         *         }
         *       ],
         *       "source_api_request_id": "4fd2ceef-0d7d-47ee-a42f-e70f78684aeb"
         *     }
         */
        PutRosterMappingsBody: {
            /** Assignments */
            assignments: components["schemas"]["RosterMappingAssignmentBody"][];
            /**
             * Source Api Request Id
             * Format: uuid
             */
            source_api_request_id: string;
        };
        pydantic__types__JsonValue: unknown;
        /**
         * ReceiptConfidence
         * @enum {string}
         */
        ReceiptConfidence: "unverified" | "inferred" | "source_backed";
        /** RefreshRun */
        RefreshRun: {
            /** Code Version */
            code_version: string;
            /**
             * Competition Id
             * Format: uuid
             */
            competition_id: string;
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            /** Completed At */
            completed_at: string | null;
            /** Endpoint Scope */
            endpoint_scope: components["schemas"]["PlannedEndpointScope"][];
            /** Error */
            error: {
                [key: string]: components["schemas"]["backend__services__datalayer__canonical_json__JsonValue"];
            } | null;
            /** Failed Request Count */
            failed_request_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Normalizer Version */
            normalizer_version: string;
            /** Request Count */
            request_count: number;
            /** Requested Through Week */
            requested_through_week: number | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["RefreshStatus"];
            /** Succeeded Request Count */
            succeeded_request_count: number;
            trigger: components["schemas"]["RefreshTrigger"];
        };
        /** RefreshRunPage */
        RefreshRunPage: {
            /** Items */
            items: components["schemas"]["RefreshRun"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** RefreshRunPageResponse */
        RefreshRunPageResponse: {
            page: components["schemas"]["RefreshRunPage"];
        };
        /** RefreshRunResponse */
        RefreshRunResponse: {
            refresh: components["schemas"]["RefreshRun"];
        };
        /**
         * RefreshStatus
         * @enum {string}
         */
        RefreshStatus: "running" | "succeeded" | "partial" | "failed" | "cancelled";
        /**
         * RefreshTrigger
         * @enum {string}
         */
        RefreshTrigger: "manual" | "generation" | "scheduled" | "backfill";
        /** RelatedStorylineExpansion */
        RelatedStorylineExpansion: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "related_storyline";
            memory: components["schemas"]["VersionedMemory_StorylineContent_"];
            reference: components["schemas"]["RelatedStorylineRef"];
        };
        /** RelatedStorylineRef */
        RelatedStorylineRef: {
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            role: components["schemas"]["RelatedStorylineRole"];
        };
        /**
         * RelatedStorylineRole
         * @enum {string}
         */
        RelatedStorylineRole: "related_arc" | "continuation" | "counterpoint";
        /** RematchCondition */
        RematchCondition: {
            /** Franchise Ids */
            franchise_ids: [
                string,
                string
            ];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "rematch";
        };
        /**
         * RequestStatus
         * @enum {string}
         */
        RequestStatus: "succeeded" | "http_error" | "transport_error" | "invalid_payload";
        /** RevisionHistoryResponse */
        RevisionHistoryResponse: {
            /** Revisions */
            revisions: components["schemas"]["CanonicalRevision"][];
        };
        /** RevisionResponse */
        RevisionResponse: {
            revision: components["schemas"]["CanonicalRevision"];
        };
        /** RosterManagerEvidence */
        RosterManagerEvidence: {
            /** Display Name */
            display_name: string;
            /**
             * Role
             * @enum {string}
             */
            role: "owner" | "co_owner";
            /** Sleeper User Id */
            sleeper_user_id: string;
            /** Team Name */
            team_name?: string | null;
        };
        /** RosterMappingAssignmentBody */
        RosterMappingAssignmentBody: {
            /** Sleeper Roster Id */
            sleeper_roster_id: string;
            /** Target */
            target: components["schemas"]["CreateFranchiseTargetBody"] | components["schemas"]["ExistingFranchiseTargetBody"];
        };
        /** RosterMappingMutationResponse */
        RosterMappingMutationResponse: {
            result: components["schemas"]["RosterMappingResult"];
        };
        /** RosterMappingResponse */
        RosterMappingResponse: {
            mapping: components["schemas"]["RosterMappingView"];
        };
        /** RosterMappingResult */
        RosterMappingResult: {
            mapping: components["schemas"]["RosterMappingView"];
            /**
             * Replay Status
             * @enum {string}
             */
            replay_status: "applied" | "deferred";
        };
        /** RosterMappingView */
        RosterMappingView: {
            /** Franchise Options */
            franchise_options: components["schemas"]["FranchiseIdentity"][];
            /** Mapped Count */
            mapped_count: number;
            /** Roster Count */
            roster_count: number;
            /** Rosters */
            rosters: components["schemas"]["ObservedRosterMapping"][];
            /** Source Api Request Id */
            source_api_request_id?: string | null;
            /** Source Observed At */
            source_observed_at?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "awaiting_source" | "needs_mapping" | "ready";
        };
        /**
         * ScopeKey
         * @description Validated stable identity for one complete endpoint response scope.
         */
        ScopeKey: {
            /** Value */
            value: string;
        };
        /** ScopeRefreshResult */
        ScopeRefreshResult: {
            /**
             * Api Request Id
             * Format: uuid
             */
            api_request_id: string;
            /** Changed Current View */
            changed_current_view: boolean;
            fetch_status: components["schemas"]["RequestStatus"];
            normalization_status: components["schemas"]["NormalizationStatus"];
            scope_key: components["schemas"]["ScopeKey"];
            /**
             * Warning Codes
             * @default []
             */
            warning_codes: string[];
        };
        /**
         * SearchDocumentQuery
         * @description Revision-grounded discovery signals and structured result filters.
         */
        SearchDocumentQuery: {
            /** Competition Season Id */
            competition_season_id?: string | null;
            /**
             * Entity Keys
             * @default []
             */
            entity_keys: string[];
            /**
             * Evidence Version Ids
             * @default []
             */
            evidence_version_ids: string[];
            /**
             * Kinds
             * @default []
             */
            kinds: components["schemas"]["MemoryKind"][];
            /**
             * Limit
             * @default 20
             */
            limit: number;
            /**
             * Related Item Ids
             * @default []
             */
            related_item_ids: string[];
            /**
             * Statuses
             * @default []
             */
            statuses: string[];
            /**
             * Tags
             * @default []
             */
            tags: string[];
            /** Text */
            text?: string | null;
            /** Week */
            week?: number | null;
        };
        /**
         * SearchMatchReason
         * @enum {string}
         */
        SearchMatchReason: "entity_overlap" | "evidence_overlap" | "related_item_overlap" | "tag_overlap" | "lexical_match" | "browse_match";
        /** SearchScoreComponents */
        SearchScoreComponents: {
            /**
             * Entity Overlap
             * @default 0
             */
            entity_overlap: number;
            /**
             * Evidence Overlap
             * @default 0
             */
            evidence_overlap: number;
            /**
             * Lexical Rank
             * @default 0
             */
            lexical_rank: number;
            /**
             * Related Item Overlap
             * @default 0
             */
            related_item_overlap: number;
            /**
             * Salience
             * @default 0
             */
            salience: number;
            /**
             * Tag Overlap
             * @default 0
             */
            tag_overlap: number;
        };
        /** SeasonRef[FactSubjectRole] */
        SeasonRef_FactSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "season";
            role: components["schemas"]["FactSubjectRole"];
        };
        /** SeasonRef[StorylineSubjectRole] */
        SeasonRef_StorylineSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "season";
            role: components["schemas"]["StorylineSubjectRole"];
        };
        /** SeasonRosterRef[FactSubjectRole] */
        SeasonRosterRef_FactSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "season_roster";
            role: components["schemas"]["FactSubjectRole"];
        };
        /** SeasonRosterRef[StorylineSubjectRole] */
        SeasonRosterRef_StorylineSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "season_roster";
            role: components["schemas"]["StorylineSubjectRole"];
        };
        /** SleeperUserRef[FactSubjectRole] */
        SleeperUserRef_FactSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /** Id */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "sleeper_user";
            role: components["schemas"]["FactSubjectRole"];
        };
        /** SleeperUserRef[StorylineSubjectRole] */
        SleeperUserRef_StorylineSubjectRole_: {
            /** Display Name */
            display_name?: string | null;
            /** Id */
            id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "sleeper_user";
            role: components["schemas"]["StorylineSubjectRole"];
        };
        /** SnapshotArtifactSummary */
        SnapshotArtifactSummary: {
            /** Byte Length */
            byte_length: number;
            /** Sha256 */
            sha256: string;
        };
        /** SnapshotFailure */
        SnapshotFailure: {
            /** Code */
            code: string;
            /** Summary */
            summary: string;
        };
        /**
         * SnapshotStatus
         * @enum {string}
         */
        SnapshotStatus: "building" | "ready" | "failed" | "expired";
        /** StorylineContent */
        StorylineContent: {
            /** Arc Type */
            arc_type?: string | null;
            /** Callback Condition */
            callback_condition?: string | null;
            /** Evidence */
            evidence: (components["schemas"]["FactEvidenceRef"] | components["schemas"]["EventEvidenceRef"])[];
            /** Headline */
            headline: string;
            /** Related Storylines */
            related_storylines: components["schemas"]["RelatedStorylineRef"][];
            /** Resolution Summary */
            resolution_summary?: string | null;
            /** Salience */
            salience: number;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["StorylineStatus"];
            /** Subjects */
            subjects: (components["schemas"]["FranchiseRef_StorylineSubjectRole_"] | components["schemas"]["PlayerRef_StorylineSubjectRole_"] | components["schemas"]["SeasonRosterRef_StorylineSubjectRole_"] | components["schemas"]["SeasonRef_StorylineSubjectRole_"] | components["schemas"]["SleeperUserRef_StorylineSubjectRole_"])[];
            /** Summary */
            summary: string;
            /** Tags */
            tags: string[];
        };
        /** StorylineCreateRequest */
        StorylineCreateRequest: {
            content: components["schemas"]["StorylineContent"];
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** StorylineEvidenceExpansion */
        StorylineEvidenceExpansion: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "storyline_evidence";
            /** Memory */
            memory: components["schemas"]["VersionedMemory_FactContent_"] | components["schemas"]["VersionedMemory_EventContent_"];
            /** Reference */
            reference: components["schemas"]["FactEvidenceRef"] | components["schemas"]["EventEvidenceRef"];
        };
        /** StorylineHistoryResponse */
        StorylineHistoryResponse: {
            /** Items */
            items: components["schemas"]["VersionedMemory_StorylineContent_"][];
        };
        /** StorylineReplaceRequest */
        StorylineReplaceRequest: {
            content: components["schemas"]["StorylineContent"];
            /** Expected Item Revision */
            expected_item_revision: number;
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** StorylineResponse */
        StorylineResponse: {
            memory: components["schemas"]["VersionedMemory_StorylineContent_"];
        };
        /**
         * StorylineStatus
         * @enum {string}
         */
        StorylineStatus: "active" | "dormant" | "resolved" | "archived";
        /**
         * StorylineSubjectRole
         * @enum {string}
         */
        StorylineSubjectRole: "focus" | "counterparty";
        /** SubmitGenerationBody */
        SubmitGenerationBody: {
            /**
             * Competition Season Id
             * Format: uuid
             */
            competition_season_id: string;
            kind: components["schemas"]["GenerationKind"];
            /** Request Text */
            request_text: string;
            /** Requested Primary Model */
            requested_primary_model: string;
            settings?: components["schemas"]["GenerationSettings"];
            /** Week End */
            week_end: number;
            /** Week Start */
            week_start: number;
        };
        /** SubmittedArticleResponse */
        SubmittedArticleResponse: {
            artifact: components["schemas"]["Artifact"];
            generation: components["schemas"]["GenerationDetail"];
            version: components["schemas"]["ArtifactVersion"];
        };
        /** TokenTotals */
        TokenTotals: {
            /**
             * Cached Input Tokens
             * @default 0
             */
            cached_input_tokens: number;
            /**
             * Input Tokens
             * @default 0
             */
            input_tokens: number;
            /**
             * Output Tokens
             * @default 0
             */
            output_tokens: number;
            /**
             * Reasoning Tokens
             * @default 0
             */
            reasoning_tokens: number;
            /**
             * Total Tokens
             * @default 0
             */
            total_tokens: number;
        };
        /** TokenUsage */
        TokenUsage: {
            /** Cached Input Tokens */
            cached_input_tokens?: number | null;
            /** Input Tokens */
            input_tokens?: number | null;
            /** Output Tokens */
            output_tokens?: number | null;
            /** Raw Provider Usage */
            raw_provider_usage?: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Reasoning Tokens */
            reasoning_tokens?: number | null;
            /** Total Tokens */
            total_tokens?: number | null;
        };
        /** ToolCall */
        ToolCall: {
            /**
             * Ai Call Id
             * Format: uuid
             */
            ai_call_id: string;
            /** Arguments */
            arguments: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            };
            /** Completed At */
            completed_at: string | null;
            /** Duration Ms */
            duration_ms: number | null;
            /** Error */
            error: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | null;
            /** Error Text */
            error_text: string | null;
            /** Full Result Text */
            full_result_text: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Implementation Version */
            implementation_version: string;
            /** Provider Tool Call Id */
            provider_tool_call_id: string | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["ToolCallStatus"];
            /** Structured Result */
            structured_result: {
                [key: string]: components["schemas"]["pydantic__types__JsonValue"];
            } | components["schemas"]["pydantic__types__JsonValue"][] | null;
            /** Tool Name */
            tool_name: string;
            /** Tool Ordinal */
            tool_ordinal: number;
        };
        /** ToolCallPage */
        ToolCallPage: {
            /** Items */
            items: components["schemas"]["ToolCallSummary"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** ToolCallPageResponse */
        ToolCallPageResponse: {
            page: components["schemas"]["ToolCallPage"];
        };
        /** ToolCallResponse */
        ToolCallResponse: {
            tool_call: components["schemas"]["ToolCall"];
        };
        /**
         * ToolCallStatus
         * @enum {string}
         */
        ToolCallStatus: "running" | "succeeded" | "failed" | "cancelled";
        /** ToolCallSummary */
        ToolCallSummary: {
            /**
             * Ai Call Id
             * Format: uuid
             */
            ai_call_id: string;
            /** Completed At */
            completed_at: string | null;
            /** Duration Ms */
            duration_ms: number | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Implementation Version */
            implementation_version: string;
            /** Provider Tool Call Id */
            provider_tool_call_id: string | null;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["ToolCallStatus"];
            /** Tool Name */
            tool_name: string;
            /** Tool Ordinal */
            tool_ordinal: number;
        };
        /**
         * TradeAssetDirection
         * @enum {string}
         */
        TradeAssetDirection: "sender_to_receiver" | "receiver_to_sender";
        /** TradeEvaluationCondition */
        TradeEvaluationCondition: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "trade_evaluation";
        };
        /** TradeEventPayload */
        TradeEventPayload: {
            /** Assets */
            assets: (components["schemas"]["PlayerTradeAsset"] | components["schemas"]["DraftPickTradeAsset"] | components["schemas"]["BudgetTradeAsset"])[];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "trade";
            /**
             * Receiver Franchise Id
             * Format: uuid
             */
            receiver_franchise_id: string;
            /**
             * Sender Franchise Id
             * Format: uuid
             */
            sender_franchise_id: string;
        };
        /** TriggerContent */
        TriggerContent: {
            /** Condition */
            condition: components["schemas"]["RematchCondition"] | components["schemas"]["TradeEvaluationCondition"];
            fire_policy: components["schemas"]["FirePolicy"];
            /** Origin Event Item Id */
            origin_event_item_id?: string | null;
            /** Resolution Reason */
            resolution_reason?: string | null;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["TriggerStatus"];
            /** Target At */
            target_at?: string | null;
            /** Target Competition Season Id */
            target_competition_season_id?: string | null;
            /** Target Storyline Item Id */
            target_storyline_item_id?: string | null;
            /** Target Week */
            target_week?: number | null;
            trigger_type: components["schemas"]["TriggerType"];
        };
        /** TriggerCreateRequest */
        TriggerCreateRequest: {
            content: components["schemas"]["TriggerContent"];
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** TriggerHistoryResponse */
        TriggerHistoryResponse: {
            /** Items */
            items: components["schemas"]["VersionedMemory_TriggerContent_"][];
        };
        /** TriggerOriginEventExpansion */
        TriggerOriginEventExpansion: {
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "trigger_origin_event";
            memory: components["schemas"]["VersionedMemory_EventContent_"];
        };
        /** TriggerReplaceRequest */
        TriggerReplaceRequest: {
            content: components["schemas"]["TriggerContent"];
            /** Expected Item Revision */
            expected_item_revision: number;
            metadata?: components["schemas"]["MemoryMutationMetadata"];
            origin: components["schemas"]["MemoryMutationOrigin"];
        };
        /** TriggerResponse */
        TriggerResponse: {
            memory: components["schemas"]["VersionedMemory_TriggerContent_"];
        };
        /**
         * TriggerStatus
         * @enum {string}
         */
        TriggerStatus: "open" | "fired" | "satisfied" | "expired" | "archived";
        /** TriggerTargetStorylineExpansion */
        TriggerTargetStorylineExpansion: {
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "trigger_target_storyline";
            memory: components["schemas"]["VersionedMemory_StorylineContent_"];
        };
        /**
         * TriggerType
         * @enum {string}
         */
        TriggerType: "rematch" | "trade_evaluation";
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** VersionedMemory[EventContent] */
        VersionedMemory_EventContent_: {
            content: components["schemas"]["EventContent-Output"];
            item: components["schemas"]["MemoryItemIdentity"];
            version: components["schemas"]["MemoryVersionMetadata"];
        };
        /** VersionedMemory[FactContent] */
        VersionedMemory_FactContent_: {
            content: components["schemas"]["FactContent-Output"];
            item: components["schemas"]["MemoryItemIdentity"];
            version: components["schemas"]["MemoryVersionMetadata"];
        };
        /** VersionedMemory[StorylineContent] */
        VersionedMemory_StorylineContent_: {
            content: components["schemas"]["StorylineContent"];
            item: components["schemas"]["MemoryItemIdentity"];
            version: components["schemas"]["MemoryVersionMetadata"];
        };
        /** VersionedMemory[TriggerContent] */
        VersionedMemory_TriggerContent_: {
            content: components["schemas"]["TriggerContent"];
            item: components["schemas"]["MemoryItemIdentity"];
            version: components["schemas"]["MemoryVersionMetadata"];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    competition_list_api_v1_competitions_get: {
        parameters: {
            query?: {
                include_archived?: boolean;
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionPageResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_competition_api_v1_competitions_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCompetitionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    competition_detail_api_v1_competitions__competition_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionOverviewResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_competition_api_v1_competitions__competition_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PatchCompetitionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    competition_season_list_api_v1_competitions__competition_id__seasons_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionSeasonPageResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_competition_season_api_v1_competitions__competition_id__seasons_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCompetitionSeasonBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionSeasonResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    competition_season_detail_api_v1_competitions__competition_id__seasons__season_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompetitionSeasonDetailResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_roster_mappings_api_v1_competitions__competition_id__seasons__season_id__roster_mappings_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RosterMappingResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_roster_mappings_api_v1_competitions__competition_id__seasons__season_id__roster_mappings_put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PutRosterMappingsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RosterMappingMutationResponse"];
                };
            };
            /** @description The competition or scoped season was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_not_found",
                     *         "summary": "competition was not found"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description The requested identity or lifecycle change conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    /**
                     * @example {
                     *       "error": {
                     *         "code": "competition_season_year_exists",
                     *         "field_errors": {
                     *           "season_year": [
                     *             "Already attached to this competition."
                     *           ]
                     *         },
                     *         "summary": "that season year is already attached to this competition"
                     *       }
                     *     }
                     */
                    "application/json": components["schemas"]["CoreErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_league_season_overview_api_v1_data_competitions__competition_id__seasons__season_id__overview_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeagueSeasonOverviewResponse"];
                };
            };
            /** @description Invalid workflow input. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The scoped data resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The requested operation conflicts with stored data. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The request or endpoint payload was rejected. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description A required datalayer dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
        };
    };
    list_refreshes_api_v1_data_competitions__competition_id__seasons__season_id__refreshes_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RefreshRunPageResponse"];
                };
            };
            /** @description Invalid workflow input. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The scoped data resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The requested operation conflicts with stored data. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The request or endpoint payload was rejected. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description A required datalayer dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
        };
    };
    run_manual_refresh_api_v1_data_competitions__competition_id__seasons__season_id__refreshes_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ManualRefreshBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ManualRefreshResponse"];
                };
            };
            /** @description Invalid workflow input. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The scoped data resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The requested operation conflicts with stored data. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The request or endpoint payload was rejected. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description A required datalayer dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
        };
    };
    get_refresh_api_v1_data_competitions__competition_id__seasons__season_id__refreshes__refresh_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                refresh_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RefreshRunResponse"];
                };
            };
            /** @description Invalid workflow input. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The scoped data resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The requested operation conflicts with stored data. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The request or endpoint payload was rejected. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description A required datalayer dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
        };
    };
    list_snapshots_api_v1_data_competitions__competition_id__seasons__season_id__snapshots_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                season_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataSnapshotPageResponse"];
                };
            };
            /** @description Invalid workflow input. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The scoped data resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The requested operation conflicts with stored data. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description The request or endpoint payload was rejected. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
            /** @description A required datalayer dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DataErrorResponse"];
                };
            };
        };
    };
    generation_history_api_v1_generations_competitions__competition_id__get: {
        parameters: {
            query?: {
                competition_season_id?: string | null;
                kind?: components["schemas"]["GenerationKind"] | null;
                limit?: number;
                offset?: number;
                rerun_of_generation_id?: string | null;
                status?: components["schemas"]["GenerationStatus"] | null;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationPageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_generation_api_v1_generations_competitions__competition_id__post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SubmitGenerationBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generation_detail_api_v1_generations_competitions__competition_id___generation_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationDetailResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ai_call_history_api_v1_generations_competitions__competition_id___generation_id__ai_calls_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                status?: components["schemas"]["AICallStatus"] | null;
                turn_number?: number | null;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AICallPageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ai_call_detail_api_v1_generations_competitions__competition_id___generation_id__ai_calls__ai_call_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                ai_call_id: string;
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AICallResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submitted_article_api_v1_generations_competitions__competition_id___generation_id__article_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubmittedArticleResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_history_api_v1_generations_competitions__competition_id___generation_id__artifacts_get: {
        parameters: {
            query?: {
                finalized?: boolean | null;
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactPageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_detail_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                artifact_id: string;
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_version_history_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__versions_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                artifact_id: string;
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactVersionPageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_version_detail_api_v1_generations_competitions__competition_id___generation_id__artifacts__artifact_id__versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                artifact_id: string;
                competition_id: string;
                generation_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactVersionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rerun_generation_api_v1_generations_competitions__competition_id___generation_id__reruns_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tool_call_history_api_v1_generations_competitions__competition_id___generation_id__tool_calls_get: {
        parameters: {
            query?: {
                ai_call_id?: string | null;
                limit?: number;
                offset?: number;
                status?: components["schemas"]["ToolCallStatus"] | null;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCallPageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    tool_call_detail_api_v1_generations_competitions__competition_id___generation_id__tool_calls__tool_call_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
                tool_call_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCallResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generation_usage_api_v1_generations_competitions__competition_id___generation_id__usage_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                generation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationUsageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    article_history_api_v1_generations_competitions__competition_id__articles_get: {
        parameters: {
            query?: {
                competition_season_id?: string | null;
                kind?: components["schemas"]["GenerationKind"] | null;
                limit?: number;
                offset?: number;
            };
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArticlePageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_context_note_api_v1_memory_competitions__competition_id__context_notes_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContextNoteCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    replace_context_note_api_v1_memory_competitions__competition_id__context_notes__item_id__put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContextNoteReplaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    context_note_history_api_v1_memory_competitions__competition_id__context_notes__item_id__history_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContextNoteHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_context_note_api_v1_memory_competitions__competition_id__context_notes_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContextNoteResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    create_event_api_v1_memory_competitions__competition_id__events_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    replace_event_api_v1_memory_competitions__competition_id__events__item_id__put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventReplaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    event_history_api_v1_memory_competitions__competition_id__events__item_id__history_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_event_api_v1_memory_competitions__competition_id__events_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    create_fact_api_v1_memory_competitions__competition_id__facts_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FactCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    replace_fact_api_v1_memory_competitions__competition_id__facts__item_id__put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FactReplaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    fact_history_api_v1_memory_competitions__competition_id__facts__item_id__history_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FactHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_fact_api_v1_memory_competitions__competition_id__facts_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FactResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    revision_history_api_v1_memory_competitions__competition_id__revisions_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_revision_api_v1_memory_competitions__competition_id__revisions__revision_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    current_revision_api_v1_memory_competitions__competition_id__revisions_current_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    search_memory_api_v1_memory_competitions__competition_id__search_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MemorySearchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemorySearchResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    create_storyline_api_v1_memory_competitions__competition_id__storylines_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StorylineCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    replace_storyline_api_v1_memory_competitions__competition_id__storylines__item_id__put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StorylineReplaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    storyline_history_api_v1_memory_competitions__competition_id__storylines__item_id__history_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StorylineHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_storyline_api_v1_memory_competitions__competition_id__storylines_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StorylineResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    create_trigger_api_v1_memory_competitions__competition_id__triggers_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TriggerCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    replace_trigger_api_v1_memory_competitions__competition_id__triggers__item_id__put: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TriggerReplaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryMutationResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    trigger_history_api_v1_memory_competitions__competition_id__triggers__item_id__history_get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TriggerHistoryResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    exact_trigger_api_v1_memory_competitions__competition_id__triggers_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "X-Correlation-ID"?: string | null;
            };
            path: {
                competition_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TriggerResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemoryErrorResponse"];
                };
            };
        };
    };
    model_catalog_api_v1_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelCatalogResponse"];
                };
            };
        };
    };
    liveness_health_live_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    readiness_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
}
