export interface paths {
    "/api/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tasks */
        get: operations["list_tasks_api_tasks_get"];
        put?: never;
        /** Create Task */
        post: operations["create_task_api_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/trash": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Trash */
        get: operations["list_trash_api_tasks_trash_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/tags": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tags */
        get: operations["list_tags_api_tasks_tags_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Task */
        get: operations["get_task_api_tasks__task_id__get"];
        put?: never;
        post?: never;
        /** Delete Task */
        delete: operations["delete_task_api_tasks__task_id__delete"];
        options?: never;
        head?: never;
        /** Update Task */
        patch: operations["update_task_api_tasks__task_id__patch"];
        trace?: never;
    };
    "/api/tasks/{task_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Task */
        post: operations["restore_task_api_tasks__task_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Purge Task */
        delete: operations["purge_task_api_tasks__task_id__purge_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/subtasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Subtask */
        post: operations["create_subtask_api_tasks__task_id__subtasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/subtasks/{subtask_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Subtask */
        delete: operations["delete_subtask_api_tasks__task_id__subtasks__subtask_id__delete"];
        options?: never;
        head?: never;
        /** Update Subtask */
        patch: operations["update_subtask_api_tasks__task_id__subtasks__subtask_id__patch"];
        trace?: never;
    };
    "/api/schedule/entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Entries
         * @description 排期条目列表（re #B5）：默认近 30 天（[今天-29, 今天]），只给一端按 30 天窗推算；
         *     可按 task_id 过滤。entry_id 不再创建即失联。
         */
        get: operations["list_entries_api_schedule_entries_get"];
        put?: never;
        /** Create Entry */
        post: operations["create_entry_api_schedule_entries_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/entries/{entry_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Entry */
        delete: operations["delete_entry_api_schedule_entries__entry_id__delete"];
        options?: never;
        head?: never;
        /** Update Entry */
        patch: operations["update_entry_api_schedule_entries__entry_id__patch"];
        trace?: never;
    };
    "/api/schedule/day": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Day View */
        get: operations["day_view_api_schedule_day_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/month": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Month View */
        get: operations["month_view_api_schedule_month_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/range": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Range View */
        get: operations["range_view_api_schedule_range_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Event */
        post: operations["create_event_api_schedule_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/events/expand": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Expand Events */
        get: operations["expand_events_api_schedule_events_expand_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/events/{event_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Event */
        get: operations["get_event_api_schedule_events__event_id__get"];
        put?: never;
        post?: never;
        /** Delete Event */
        delete: operations["delete_event_api_schedule_events__event_id__delete"];
        options?: never;
        head?: never;
        /** Update Event */
        patch: operations["update_event_api_schedule_events__event_id__patch"];
        trace?: never;
    };
    "/api/schedule/conflicts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Find Conflicts */
        get: operations["find_conflicts_api_schedule_conflicts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/schedule/free-slots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Free Slots */
        get: operations["free_slots_api_schedule_free_slots_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Goals */
        get: operations["list_goals_api_goals_get"];
        put?: never;
        /** Create Goal */
        post: operations["create_goal_api_goals_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/trash": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Trash
         * @description 回收站：软删目标列表（含 key_results 与 deleted_at，re #B2）。
         */
        get: operations["list_trash_api_goals_trash_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/{goal_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Goal */
        get: operations["get_goal_api_goals__goal_id__get"];
        put?: never;
        post?: never;
        /** Delete Goal */
        delete: operations["delete_goal_api_goals__goal_id__delete"];
        options?: never;
        head?: never;
        /** Update Goal */
        patch: operations["update_goal_api_goals__goal_id__patch"];
        trace?: never;
    };
    "/api/goals/{goal_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Goal */
        post: operations["restore_goal_api_goals__goal_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/{goal_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Purge Goal
         * @description 硬删目标（级联 KR）。仅回收站中的可 purge：未软删 → 409。
         */
        delete: operations["purge_goal_api_goals__goal_id__purge_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/{goal_id}/key-results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Key Result */
        post: operations["add_key_result_api_goals__goal_id__key_results_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/key-results/{kr_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Key Result */
        delete: operations["delete_key_result_api_goals_key_results__kr_id__delete"];
        options?: never;
        head?: never;
        /** Update Key Result */
        patch: operations["update_key_result_api_goals_key_results__kr_id__patch"];
        trace?: never;
    };
    "/api/goals/{goal_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Goal Progress */
        get: operations["goal_progress_api_goals__goal_id__progress_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/habits": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Habits */
        get: operations["list_habits_api_habits_get"];
        put?: never;
        /** Create Habit */
        post: operations["create_habit_api_habits_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/habits/{habit_id}/check-in": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Check In */
        post: operations["check_in_api_habits__habit_id__check_in_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/habits/{habit_id}/uncheck": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Uncheck
         * @description 撤销一笔打卡：date 缺省=今天（re #B3，openapi schema 与实现对齐）。
         */
        post: operations["uncheck_api_habits__habit_id__uncheck_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/habits/{habit_id}/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Logs */
        get: operations["list_logs_api_habits__habit_id__logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/habits/{habit_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Habit */
        delete: operations["delete_habit_api_habits__habit_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/journal/today": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Today Entry */
        get: operations["today_entry_api_journal_today_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/journal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Entries */
        get: operations["list_entries_api_journal_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/journal/{day}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Entry */
        get: operations["get_entry_api_journal__day__get"];
        /** Upsert Entry */
        put: operations["upsert_entry_api_journal__day__put"];
        post?: never;
        /** Delete Entry */
        delete: operations["delete_entry_api_journal__day__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start */
        post: operations["start_api_focus_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Stop */
        post: operations["stop_api_focus_stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current */
        get: operations["current_api_focus_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Logs */
        get: operations["logs_api_focus_logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/stats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stats */
        get: operations["stats_api_focus_stats_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/focus/logs/{log_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Log
         * @description 删除一条已结束的计时记录（re k3#048 残留清理诉求）。
         *     运行中的计时不可直接删（先停后删），409 防误删破坏 current 指针语义。
         */
        delete: operations["delete_log_api_focus_logs__log_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Files */
        get: operations["list_files_api_files_get"];
        put?: never;
        /**
         * Upload
         * @description 上传文件。notes 为 multipart 表单域（re #B6：原 query 传法表单域会被静默忽略）。
         */
        post: operations["upload_api_files_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/links": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Link */
        post: operations["create_link_api_files_links_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/trash": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Trash */
        get: operations["list_trash_api_files_trash_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Task Files */
        get: operations["task_files_api_files_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get File */
        get: operations["get_file_api_files__file_id__get"];
        put?: never;
        post?: never;
        /** Soft Delete */
        delete: operations["soft_delete_api_files__file_id__delete"];
        options?: never;
        head?: never;
        /** Update Notes */
        patch: operations["update_notes_api_files__file_id__patch"];
        trace?: never;
    };
    "/api/files/{file_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore */
        post: operations["restore_api_files__file_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/{file_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Purge */
        delete: operations["purge_api_files__file_id__purge_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/{file_id}/attach/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Attach */
        post: operations["attach_api_files__file_id__attach__task_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/files/{file_id}/detach/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Detach */
        post: operations["detach_api_files__file_id__detach__task_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Notifications */
        get: operations["list_notifications_api_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notifications/unread": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Unread */
        get: operations["unread_api_notifications_unread_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notifications/{notification_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Read */
        post: operations["mark_read_api_notifications__notification_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notifications/read-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark All Read */
        post: operations["mark_all_read_api_notifications_read_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/stats/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Summary */
        get: operations["summary_api_stats_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/stats/daily": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Daily */
        get: operations["daily_api_stats_daily_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/stats/by-tag": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** By Tag */
        get: operations["by_tag_api_stats_by_tag_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/stats/by-priority": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** By Priority */
        get: operations["by_priority_api_stats_by_priority_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/stats/risk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Risk */
        get: operations["risk_api_stats_risk_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Settings */
        get: operations["get_settings_api_settings_get"];
        /** Put Settings */
        put: operations["put_settings_api_settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ical/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export
         * @description response_class=Response（media_type None）：openapi 不再自动误标
         *     application/json 空 schema，200 只声明 text/calendar（re #048）。
         */
        get: operations["export_api_ical_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ical/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Ics */
        post: operations["import_ics_api_ical_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Attachment
         * @description 上传对话附件：落盘 + 立即解析缓存（extracted_text）。
         *     返回 file_id 供聊天时以 attachment_ids 引用；image 落 needs_vision。
         */
        post: operations["upload_attachment_ai_attachments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/chat/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat Stream */
        post: operations["chat_stream_ai_chat_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_ai_conversations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Conversation Detail */
        get: operations["conversation_detail_ai_conversations__cid__get"];
        put?: never;
        post?: never;
        /** Delete Conversation */
        delete: operations["delete_conversation_ai_conversations__cid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/configs/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** List Available Models */
        post: operations["list_available_models_ai_configs_models_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/configs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Configs */
        get: operations["list_configs_ai_configs_get"];
        put?: never;
        /** Create Config */
        post: operations["create_config_ai_configs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/configs/{cid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Config */
        put: operations["update_config_ai_configs__cid__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/configs/{cid}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Config */
        post: operations["enable_config_ai_configs__cid__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/runs/{run_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Run */
        post: operations["cancel_run_ai_runs__run_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/actions/{action_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Action */
        post: operations["approve_action_ai_actions__action_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/actions/{action_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Action */
        post: operations["reject_action_ai_actions__action_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Grants */
        get: operations["list_grants_ai_grants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/grants/{grant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Grant */
        delete: operations["delete_grant_ai_grants__grant_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}/resume/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Stream
         * @description 审批结案后恢复：取会话最后 assistant 消息的 history + 该轮全部 deferred 调用的
         *     结案结果，构造 DeferredToolResults 重启新 execution。
         *     回填范围 = history 末条模型响应中「尚未结算」的工具调用（re #028：同响应可混合
         *     safe/readonly 直行调用——其结果已在 trailing ModelRequest 里、不落审批表，须从
         *     末条响应的调用中扣除；pydantic-ai 恢复时对已结算调用自动以 skip 覆盖，路由层若
         *     重复回填反而触发「already executed」UserError。剩余 open 调用一个不漏，缺任一
         *     即 UserError 崩流，re #020 k3 major）；
         *     仍有 pending 审批卡 → 400 + 未决清单（typed），不启动流；
         *     该批次已被消费（confirmed 已转 executed / 源 run 已记 resumed_by_runs）→
         *     400 typed consumed，幂等拒绝，不重复回填（re #023④）。
         */
        post: operations["resume_stream_ai_conversations__cid__resume_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}/plans/{plan_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Plan
         * @description 批准计划：steps 组装为执行指令，作为同一会话的新用户消息切回普通模式执行（SSE 流）。
         */
        post: operations["approve_plan_ai_conversations__cid__plans__plan_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}/plans/{plan_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Plan */
        post: operations["reject_plan_ai_conversations__cid__plans__plan_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Skills */
        get: operations["list_skills_ai_skills_get"];
        put?: never;
        /** Create Skill */
        post: operations["create_skill_ai_skills_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/skills/{sid}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Skill */
        post: operations["enable_skill_ai_skills__sid__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/skills/disable-active": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Disable Active Skill
         * @description 停用当前激活的用户技能（内置技能不动；无激活技能时幂等 ok，re k3#049 观察①）。
         *     instructions 组装按 enabled 过滤（prompts._skill_text），停用后其内容自然
         *     退出系统提示，无需另行清理。
         */
        post: operations["disable_active_skill_ai_skills_disable_active_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/skills/{sid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Skill */
        delete: operations["delete_skill_ai_skills__sid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/mcp/servers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Mcp Servers */
        get: operations["list_mcp_servers_ai_mcp_servers_get"];
        put?: never;
        /** Create Mcp Server */
        post: operations["create_mcp_server_ai_mcp_servers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/mcp/servers/{sid}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Mcp Server */
        put: operations["update_mcp_server_ai_mcp_servers__sid__put"];
        post?: never;
        /** Delete Mcp Server */
        delete: operations["delete_mcp_server_ai_mcp_servers__sid__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/mcp/servers/{sid}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Mcp Server */
        post: operations["enable_mcp_server_ai_mcp_servers__sid__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/mcp/servers/{sid}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Test Mcp Server
         * @description 连通性测试：连接 + list_tools，回写 last_status/last_error（错误已脱敏截断）。
         *     B1：untrusted 的 stdio 服务器直接 403，不拉起子进程。
         */
        post: operations["test_mcp_server_ai_mcp_servers__sid__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/mcp/servers/{sid}/tools": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Mcp Server Tools
         * @description 工具清单（60s TTL 缓存；PUT/enable/DELETE 时主动失效，清账 B2）。
         *     B1：untrusted 的 stdio 服务器直接 403，不拉起子进程。
         */
        get: operations["list_mcp_server_tools_ai_mcp_servers__sid__tools_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/reports/{report_type}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Report */
        post: operations["create_report_ai_reports__report_type__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Reports */
        get: operations["list_reports_ai_reports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/briefing/today": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Today Briefing
         * @description 幂等取当日晨报；无配置或 AI 失败自动降级规则文案，恒 200。
         */
        get: operations["today_briefing_ai_briefing_today_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/reports/{report_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Report Detail */
        get: operations["report_detail_ai_reports__report_id__get"];
        put?: never;
        post?: never;
        /** Delete Report */
        delete: operations["delete_report_ai_reports__report_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ledger": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Entries */
        get: operations["list_entries_api_ledger_get"];
        put?: never;
        /** Create Entry */
        post: operations["create_entry_api_ledger_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ledger/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Summary */
        get: operations["summary_api_ledger_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ledger/{entry_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Entry */
        get: operations["get_entry_api_ledger__entry_id__get"];
        /** Replace Entry */
        put: operations["replace_entry_api_ledger__entry_id__put"];
        post?: never;
        /** Delete Entry */
        delete: operations["delete_entry_api_ledger__entry_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/ledger/{entry_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Entry */
        post: operations["restore_entry_api_ledger__entry_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Bills */
        get: operations["list_bills_api_bills_get"];
        put?: never;
        /** Create */
        post: operations["create_api_bills_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills/{bill_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["read_api_bills__bill_id__get"];
        /** Replace */
        put: operations["replace_api_bills__bill_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills/{bill_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["history_api_bills__bill_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills/occurrences/{occurrence_id}/pay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pay */
        post: operations["pay_api_bills_occurrences__occurrence_id__pay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills/occurrences/{occurrence_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Occurrence */
        get: operations["read_occurrence_api_bills_occurrences__occurrence_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/bills/occurrences/{occurrence_id}/skip": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Skip */
        post: operations["skip_api_bills_occurrences__occurrence_id__skip_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/inbox": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Items */
        get: operations["list_items_api_inbox_get"];
        put?: never;
        /** Capture */
        post: operations["capture_api_inbox_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/inbox/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Item */
        get: operations["get_item_api_inbox__item_id__get"];
        /** Revise */
        put: operations["revise_api_inbox__item_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/inbox/{item_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Item */
        post: operations["apply_item_api_inbox__item_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/inbox/{item_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject */
        post: operations["reject_api_inbox__item_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/watch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Watch */
        get: operations["read_watch_api_research_projects__project_id__watch_get"];
        /** Configure Watch */
        put: operations["configure_watch_api_research_projects__project_id__watch_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/watch/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Watch */
        post: operations["run_watch_api_research_projects__project_id__watch_run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_api_research_projects_get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_api_research_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["detail_api_research_projects__project_id__get"];
        /** Update Project */
        put: operations["update_project_api_research_projects__project_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive */
        post: operations["archive_api_research_projects__project_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/sources/gather": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Gather */
        post: operations["gather_api_research_projects__project_id__sources_gather_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Source */
        post: operations["add_source_api_research_projects__project_id__sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/materials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Attach Material */
        post: operations["attach_material_api_research_projects__project_id__materials_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/sources/{source_id}/fetch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Fetch Source */
        post: operations["fetch_source_api_research_projects__project_id__sources__source_id__fetch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/plans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Plan History */
        get: operations["plan_history_api_research_projects__project_id__plans_get"];
        put?: never;
        /** Preview Plan */
        post: operations["preview_plan_api_research_projects__project_id__plans_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/replan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Replan */
        post: operations["preview_replan_api_research_projects__project_id__replan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/extensions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Extension */
        post: operations["preview_extension_api_research_projects__project_id__extensions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Revision */
        post: operations["preview_revision_api_research_projects__project_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Feedback */
        get: operations["list_feedback_api_research_projects__project_id__feedback_get"];
        put?: never;
        /** Record Feedback */
        post: operations["record_feedback_api_research_projects__project_id__feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/projects/{project_id}/feedback/{feedback_id}/withdraw": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Withdraw Feedback */
        post: operations["withdraw_feedback_api_research_projects__project_id__feedback__feedback_id__withdraw_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Plan */
        get: operations["get_plan_api_research_plans__plan_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/research/plans/{plan_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Plan */
        post: operations["apply_plan_api_research_plans__plan_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Followups */
        get: operations["list_followups_api_followups_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status */
        get: operations["status_api_followups_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/preferences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Preferences */
        put: operations["preferences_api_followups_preferences_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Check */
        post: operations["check_api_followups_check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/{followup_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Followup */
        get: operations["get_followup_api_followups__followup_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/{followup_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply */
        post: operations["apply_api_followups__followup_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/followups/{followup_id}/respond": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Respond */
        post: operations["respond_api_followups__followup_id__respond_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/materials/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search */
        get: operations["search_api_materials_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/materials/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["read_api_materials__file_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/web-services": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Web Services */
        get: operations["get_web_services_ai_web_services_get"];
        /** Put Web Services */
        put: operations["put_web_services_ai_web_services_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/web-services/credentials/tavily": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Put Tavily Key */
        put: operations["put_tavily_key_ai_web_services_credentials_tavily_put"];
        post?: never;
        /** Delete Tavily Key */
        delete: operations["delete_tavily_key_ai_web_services_credentials_tavily_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/web-services/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Search Web */
        post: operations["search_web_ai_web_services_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/web-services/fetch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Fetch Web */
        post: operations["fetch_web_ai_web_services_fetch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/vision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Vision */
        get: operations["get_vision_ai_vision_get"];
        /** Save Vision */
        put: operations["save_vision_ai_vision_put"];
        post?: never;
        /** Clear Vision */
        delete: operations["clear_vision_ai_vision_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/workspaces/{surface}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Workspace */
        get: operations["workspace_ai_workspaces__surface__get"];
        /** Save Workspace */
        put: operations["save_workspace_ai_workspaces__surface__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}/pending/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Pending */
        post: operations["cancel_pending_ai_conversations__cid__pending_cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ai/conversations/{cid}/state": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Conversation State */
        get: operations["conversation_state_ai_conversations__cid__state_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/shutdown": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Shutdown */
        post: operations["shutdown_shutdown_post"];
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
        /**
         * ActionResolveOut
         * @description 审批/计划结案端点的统一返回体（re #013 minor：typed schema）。
         *     re #023 建议③：ready_to_resume=该 action 所属 run 批次内已无 pending
         *     （全部 confirmed/rejected/executed）——前端只在 ready 后才开 resume 流。
         */
        ActionResolveOut: {
            /**
             * Ok
             * @default true
             */
            ok?: boolean;
            /**
             * Resume
             * @default
             */
            resume?: string;
            /**
             * Ready To Resume
             * @default false
             */
            ready_to_resume?: boolean;
        };
        /** AddSourceInput */
        AddSourceInput: {
            /** Url */
            url: string;
            /**
             * Title
             * @default
             */
            title?: string;
            /**
             * Refresh
             * @default false
             */
            refresh?: boolean;
        };
        /** ArchiveInput */
        ArchiveInput: {
            /** Version */
            version: number;
            /**
             * Archived
             * @default true
             */
            archived?: boolean;
        };
        /** Assignment */
        Assignment: {
            /** Unit Index */
            unit_index: number;
            /** Date */
            date: string;
            /** Start */
            start: string;
            /** End */
            end: string;
        };
        /**
         * AttachmentOut
         * @description 对话附件上传回包（re #048）：file_id 供聊天 attachment_ids 引用。
         */
        AttachmentOut: {
            /** File Id */
            file_id: number;
            /** Name */
            name: string;
            /** Kind */
            kind: string;
            /** Parse Status */
            parse_status: string;
        };
        /** BillCreate */
        BillCreate: {
            /** Title */
            title: string;
            /** Amount */
            amount?: number | string | null;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 居住
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /**
             * Remind Days
             * @default 3
             */
            remind_days?: number;
            /**
             * Enabled
             * @default true
             */
            enabled?: boolean;
            /**
             * First Due
             * Format: date
             */
            first_due: string;
            /**
             * Cycle
             * @default monthly
             * @enum {string}
             */
            cycle?: "once" | "weekly" | "monthly" | "yearly";
            /** Request Key */
            request_key: string;
        };
        /** BillDetails */
        BillDetails: {
            /** Title */
            title: string;
            /** Amount */
            amount?: string | null;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 居住
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /**
             * Remind Days
             * @default 3
             */
            remind_days?: number;
            /**
             * Enabled
             * @default true
             */
            enabled?: boolean;
        };
        /** BillHistory */
        BillHistory: {
            /** Items */
            items: components["schemas"]["BillOccurrenceRead"][];
            /** Next Before */
            next_before: number | null;
        };
        /** BillOccurrenceRead */
        BillOccurrenceRead: {
            /** Id */
            id: number;
            /** Bill Id */
            bill_id: number;
            /** Sequence */
            sequence: number;
            /**
             * Due
             * Format: date
             */
            due: string;
            details: components["schemas"]["BillDetails"];
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "paid" | "skipped";
            /** Version */
            version: number;
            ledger_entry: components["schemas"]["EntryRead"] | null;
            /** Resolution */
            resolution: {
                [key: string]: unknown;
            } | null;
            /** Resolved At */
            resolved_at: string | null;
        };
        /** BillPage */
        BillPage: {
            /** Items */
            items: components["schemas"]["BillRead"][];
            /** Total */
            total: number;
            /** Offset */
            offset: number;
            /** Limit */
            limit: number;
        };
        /** BillPayment */
        BillPayment: {
            /** Version */
            version: number;
            /**
             * Day
             * Format: date
             */
            day: string;
            /** Amount */
            amount: number | string;
            /** Account */
            account: string;
            /** Existing Entry Id */
            existing_entry_id?: number | null;
            /** Source File Id */
            source_file_id?: number | null;
            /**
             * Source Excerpt
             * @default
             */
            source_excerpt?: string;
        };
        /** BillRead */
        BillRead: {
            /** Id */
            id: number;
            /**
             * First Due
             * Format: date
             */
            first_due: string;
            /** Cycle */
            cycle: string;
            /** Version */
            version: number;
            details: components["schemas"]["BillDetails"];
            pending: components["schemas"]["BillOccurrenceRead"] | null;
        };
        /** BillSkip */
        BillSkip: {
            /** Version */
            version: number;
            /** Reason */
            reason: string;
        };
        /** BillUpdate */
        BillUpdate: {
            /** Title */
            title: string;
            /** Amount */
            amount?: number | string | null;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 居住
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /**
             * Remind Days
             * @default 3
             */
            remind_days?: number;
            /**
             * Enabled
             * @default true
             */
            enabled?: boolean;
            /** Version */
            version: number;
        };
        /** Body_import_ics_api_ical_import_post */
        Body_import_ics_api_ical_import_post: {
            /** File */
            file: string;
        };
        /** Body_upload_api_files_post */
        Body_upload_api_files_post: {
            /** File */
            file: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
        };
        /** Body_upload_attachment_ai_attachments_post */
        Body_upload_attachment_ai_attachments_post: {
            /** File */
            file: string;
        };
        /** ByDayItem */
        ByDayItem: {
            /** Date */
            date: string;
            /** Minutes */
            minutes: number;
        };
        /** ByTaskItem */
        ByTaskItem: {
            /** Task Title */
            task_title: string;
            /** Minutes */
            minutes: number;
        };
        /**
         * CancelOut
         * @description 运行取消回包（re #048）：无该 run 令牌时 ok=false。
         */
        CancelOut: {
            /** Ok */
            ok: boolean;
        };
        /** CancelPendingBody */
        CancelPendingBody: {
            /** Run Id */
            run_id: string;
        };
        /** CancelPendingOut */
        CancelPendingOut: {
            /**
             * Ok
             * @default true
             */
            ok?: boolean;
        };
        /** Candidate */
        Candidate: {
            /**
             * Source File Id
             * @description 附件上下文提供的材料编号；纯文字输入留空。不是文件名或路径。
             */
            source_file_id?: number | null;
            /**
             * Item Key
             * @description 同一原文事项的稳定位置；单笔收据用 receipt-total，多行用 p1-row2。重试不要换键。
             */
            item_key: string;
            /**
             * Source Excerpt
             * @description 支持此条目的原文摘录；保留实际日期、金额等依据，不能编造。
             */
            source_excerpt: string;
            /**
             * Uncertainty
             * @default
             */
            uncertainty?: string;
            /** Proposal */
            proposal: components["schemas"]["TaskProposal"] | components["schemas"]["EventProposal"] | components["schemas"]["LedgerProposal-Input"];
        };
        /** CaptureBatch */
        CaptureBatch: {
            /** Capture Key */
            capture_key: string;
            /** Items */
            items: components["schemas"]["Candidate"][];
        };
        /** CatalogModel */
        CatalogModel: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** CategoryTotal */
        CategoryTotal: {
            /** Category */
            category: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: string;
            /** Count */
            count: number;
        };
        /** ChatBody */
        ChatBody: {
            /** Message */
            message: string;
            /** Research Project Id */
            research_project_id?: number | null;
            /** Conversation Id */
            conversation_id?: number | null;
            /**
             * Attachment Ids
             * @default []
             */
            attachment_ids?: number[];
            /**
             * Plan Mode
             * @default false
             */
            plan_mode?: boolean;
        };
        /** CheckInOut */
        CheckInOut: {
            /** Id */
            id: number;
            /** Habit Id */
            habit_id: number;
            /** Date */
            date: string;
            /** Count */
            count: number;
        };
        /** ConfigBody */
        ConfigBody: {
            /** Name */
            name: string;
            /**
             * Provider Kind
             * @default openai_compat
             * @enum {string}
             */
            provider_kind?: "openai_compat" | "openai_responses" | "anthropic";
            /** Model */
            model: string;
            /** Base Url */
            base_url?: string | null;
            /** Api Key */
            api_key?: string | null;
            /**
             * Price Input
             * @default 0
             */
            price_input?: number;
            /**
             * Price Output
             * @default 0
             */
            price_output?: number;
            /**
             * Request Limit
             * @default 30
             */
            request_limit?: number;
            /** Context Window */
            context_window?: number | null;
            /** Max Output Tokens */
            max_output_tokens?: number | null;
            /** Reasoning Effort */
            reasoning_effort?: ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max") | null;
            /**
             * Input Modalities
             * @default [
             *       "text"
             *     ]
             */
            input_modalities?: ("text" | "image" | "audio" | "video")[];
        };
        /**
         * ConfigOut
         * @description AI 配置列表项（re #047：前端 AiConfigInfo 手写收敛依据；api_key 敏感永不回显）。
         */
        ConfigOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Provider Kind */
            provider_kind: string;
            /** Model */
            model: string;
            /** Base Url */
            base_url?: string | null;
            /** Enabled */
            enabled: boolean;
            /** Context Window */
            context_window?: number | null;
            /** Max Output Tokens */
            max_output_tokens?: number | null;
            /** Reasoning Effort */
            reasoning_effort?: ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max") | null;
            /**
             * Input Modalities
             * @default [
             *       "text"
             *     ]
             */
            input_modalities?: ("text" | "image" | "audio" | "video")[];
            /**
             * Has Api Key
             * @default false
             */
            has_api_key?: boolean;
            /**
             * Request Limit
             * @default 30
             */
            request_limit?: number;
            /**
             * Price Input
             * @default 0
             */
            price_input?: number;
            /**
             * Price Output
             * @default 0
             */
            price_output?: number;
        };
        /**
         * ConflictItemOut
         * @description 冲突项：event 展开条目或任务排期条目（字段并集，按存在字段判别）。
         */
        ConflictItemOut: {
            /** Event Id */
            event_id?: number | null;
            /** Entry Id */
            entry_id?: number | null;
            /** Task Id */
            task_id?: number | null;
            /** Title */
            title: string;
            /** Date */
            date?: string | null;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Location */
            location?: string | null;
            /** Category */
            category?: string | null;
            /** Estimated Minutes */
            estimated_minutes?: number | null;
            /** Source */
            source?: string | null;
            /** Note */
            note?: string | null;
        };
        /** ConflictOut */
        ConflictOut: {
            /** Date */
            date: string;
            /** Items */
            items: components["schemas"]["ConflictItemOut"][];
        };
        /**
         * ConversationOut
         * @description 会话列表项（re #048）：updated_at 为 ISO 串。
         */
        ConversationOut: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Updated At */
            updated_at: string;
        };
        /** ConversationStateOut */
        ConversationStateOut: {
            /** Conversation Id */
            conversation_id: number;
            /** Active Run Id */
            active_run_id: string | null;
            /** Latest Run Id */
            latest_run_id: string | null;
            /** Status */
            status: string;
            /** Approvals */
            approvals: {
                [key: string]: unknown;
            }[];
            /** Plan */
            plan: {
                [key: string]: unknown;
            } | null;
            /** Can Resume */
            can_resume: boolean;
            /** Message Count */
            message_count: number;
            /** Archive Count */
            archive_count: number;
            /** Working Rounds */
            working_rounds: number;
            /** Summary */
            summary: string;
            /** Model */
            model: string;
            /** Context Window */
            context_window: number | null;
        };
        /**
         * CreatedOut
         * @description 创建类端点的最小回包：只回新行 id，调用方随后重拉列表（re #047）。
         */
        CreatedOut: {
            /** Id */
            id: number;
        };
        /** CredentialBody */
        CredentialBody: {
            /**
             * Api Key
             * Format: password
             */
            api_key: string;
        };
        /** CredentialOut */
        CredentialOut: {
            /** Tavily Has Api Key */
            tavily_has_api_key: boolean;
        };
        /** CurrencyTotal */
        CurrencyTotal: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /** Income */
            income: string;
            /** Expense */
            expense: string;
            /** Net */
            net: string;
            /** Count */
            count: number;
            /** Categories */
            categories: components["schemas"]["CategoryTotal"][];
        };
        /**
         * DayItemOut
         * @description 统一日视图条目：event（独立日程，含 event_id/date/location/category）
         *     与 task（任务排期，含 task_id）按 kind 判别；两者字段取并集。
         */
        DayItemOut: {
            /** Kind */
            kind: string;
            /** Event Id */
            event_id?: number | null;
            /** Task Id */
            task_id?: number | null;
            /** Title */
            title: string;
            /** Date */
            date?: string | null;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Location */
            location?: string | null;
            /** Category */
            category?: string | null;
            /** Repeat Note */
            repeat_note?: string | null;
        };
        /** DayViewOut */
        DayViewOut: {
            /** Date */
            date: string;
            /** Items */
            items: components["schemas"]["DayItemOut"][];
        };
        /** Draft */
        Draft: {
            /**
             * Text
             * @default
             */
            text?: string;
            /**
             * Attachments
             * @default []
             */
            attachments?: components["schemas"]["DraftAttachment"][];
        };
        /** DraftAttachment */
        DraftAttachment: {
            /** Id */
            id: number;
            /** Name */
            name: string;
        };
        /**
         * EnableOut
         * @description 启用/切换类端点的统一回包（re #038：McpEnableResult 手写收敛依据）。
         */
        EnableOut: {
            /**
             * Ok
             * @default true
             */
            ok?: boolean;
            /** Enabled */
            enabled?: boolean | null;
        };
        /** EntryCreate */
        EntryCreate: {
            /**
             * Day
             * Format: date
             */
            day: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: number | string;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 未分类
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Source File Id */
            source_file_id?: number | null;
            /**
             * Source Excerpt
             * @default
             */
            source_excerpt?: string;
            /** Idempotency Key */
            idempotency_key?: string | null;
        };
        /** EntryPage */
        EntryPage: {
            /** Items */
            items: components["schemas"]["EntryRead"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** EntryRead */
        EntryRead: {
            /** Id */
            id: number;
            /**
             * Day
             * Format: date
             */
            day: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: string;
            /** Amount Minor */
            amount_minor: number;
            /**
             * Currency
             * @enum {string}
             */
            currency: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /** Category */
            category: string;
            /** Account */
            account: string;
            /** Payee */
            payee: string;
            /** Notes */
            notes: string;
            /** Source File Id */
            source_file_id: number | null;
            /** Source Excerpt */
            source_excerpt: string;
            /** Version */
            version: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Deleted At */
            deleted_at: string | null;
        };
        /** EntryReplace */
        EntryReplace: {
            /**
             * Day
             * Format: date
             */
            day: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: number | string;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 未分类
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Source File Id */
            source_file_id?: number | null;
            /**
             * Source Excerpt
             * @default
             */
            source_excerpt?: string;
            /** Version */
            version: number;
        };
        /**
         * EventDetailOut
         * @description 独立日程详情（re #033）：date 为 ISO 字符串（与既有消费面一致）；repeat_note 透出。
         */
        EventDetailOut: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Date */
            date: string;
            /** Start Time */
            start_time: string | null;
            /** End Time */
            end_time: string | null;
            /** Location */
            location: string;
            /** Category */
            category: string;
            /** Recur Rrule */
            recur_rrule: string | null;
            /** Notes */
            notes: string;
            /** Repeat Note */
            repeat_note?: string | null;
            /**
             * Remind Offsets
             * @default []
             */
            remind_offsets?: number[];
            /** Reminder Time */
            reminder_time?: string | null;
        };
        /** EventDraft */
        EventDraft: {
            /** Title */
            title: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /**
             * Location
             * @default
             */
            location?: string;
            /**
             * Category
             * @default general
             */
            category?: string;
            /** Recur Rrule */
            recur_rrule?: string | null;
            /** Repeat Note */
            repeat_note?: string | null;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Remind Offsets */
            remind_offsets?: number[];
            /** Reminder Time */
            reminder_time?: string | null;
        };
        /** EventProposal */
        EventProposal: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "event";
            data: components["schemas"]["EventDraft"];
        };
        /** EventUpdate */
        EventUpdate: {
            /** Title */
            title?: string | null;
            /** Date */
            date?: string | null;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Location */
            location?: string | null;
            /** Category */
            category?: string | null;
            /** Recur Rrule */
            recur_rrule?: string | null;
            /** Notes */
            notes?: string | null;
            /** Remind Offsets */
            remind_offsets?: number[] | null;
            /** Reminder Time */
            reminder_time?: string | null;
        };
        /**
         * ExpandedEventOut
         * @description events/expand：RRULE 展开后的日程出现（含单双周），周视图数据源。
         */
        ExpandedEventOut: {
            /** Event Id */
            event_id: number;
            /** Title */
            title: string;
            /** Date */
            date: string;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Location */
            location?: string | null;
            /** Category */
            category?: string | null;
            /** Repeat Note */
            repeat_note?: string | null;
        };
        /** ExtensionDraft */
        ExtensionDraft: {
            /** Version */
            version: number;
            /** Rationale */
            rationale: string;
            /**
             * Steps
             * @description 按先后顺序列步骤；不提供时间点或模型生成的任务编号。程序负责排程。
             */
            steps: components["schemas"]["StepDraft"][];
            /**
             * Feedback Ids
             * @description 本方案回应的真实反馈编号；不填写即为独立追加阶段。
             */
            feedback_ids?: number[];
        };
        /** FeedbackCreate */
        FeedbackCreate: {
            /**
             * Note
             * @description 用户自述的收获、困难或希望调整的内容，不推断掌握程度。
             */
            note: string;
            /**
             * Task Link Id
             * @description 可选项目任务记录id，来自tasks[].id，不是task_id。
             */
            task_link_id?: number | null;
            /**
             * Difficulty
             * @default unspecified
             * @enum {string}
             */
            difficulty?: "too_easy" | "suitable" | "too_hard" | "unspecified";
            /** Actual Minutes */
            actual_minutes?: number | null;
            /** Version */
            version: number;
            /** Request Key */
            request_key: string;
        };
        /** FeedbackPage */
        FeedbackPage: {
            /** Items */
            items: components["schemas"]["FeedbackRead"][];
            /** Total */
            total: number;
            /** Next Before */
            next_before?: number | null;
        };
        /** FeedbackRead */
        FeedbackRead: {
            /**
             * Note
             * @description 用户自述的收获、困难或希望调整的内容，不推断掌握程度。
             */
            note: string;
            /**
             * Task Link Id
             * @description 可选项目任务记录id，来自tasks[].id，不是task_id。
             */
            task_link_id?: number | null;
            /**
             * Difficulty
             * @default unspecified
             * @enum {string}
             */
            difficulty?: "too_easy" | "suitable" | "too_hard" | "unspecified";
            /** Actual Minutes */
            actual_minutes?: number | null;
            /** Id */
            id: number;
            /** Project Id */
            project_id: number;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "withdrawn";
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Applied Plan Ids */
            applied_plan_ids?: number[];
        };
        /** FetchBody */
        FetchBody: {
            /** Url */
            url: string;
            /** Provider */
            provider?: ("builtin" | "tavily" | "mcp") | null;
        };
        /** FetchOut */
        FetchOut: {
            /** Ok */
            ok: boolean;
            /** Url */
            url: string;
            /** Content */
            content?: string | null;
            /** Error */
            error?: string | null;
        };
        /** FileOut */
        FileOut: {
            /** Id */
            id: number;
            /** Original Name */
            original_name: string;
            /** Storage Path */
            storage_path: string;
            /** Size */
            size: number;
            /** Mime Type */
            mime_type: string;
            /** Notes */
            notes: string;
            /** Source Url */
            source_url?: string | null;
            /** Resource Type */
            resource_type: string;
            /** Parse Status */
            parse_status: string;
            /**
             * Uploaded At
             * Format: date-time
             */
            uploaded_at: string;
        };
        /** FocusStatsOut */
        FocusStatsOut: {
            /** By Day */
            by_day: components["schemas"]["ByDayItem"][];
            /** By Task */
            by_task: components["schemas"]["ByTaskItem"][];
            /** Total Minutes */
            total_minutes: number;
        };
        /**
         * FocusStopMissOut
         * @description stop 落空（无进行中计时或目标已结账）的回包；extra=forbid 保证
         *     stop 端点 TimeLogOut | FocusStopMissOut 二选一互不误配。
         */
        FocusStopMissOut: {
            /**
             * Ok
             * @default false
             */
            ok?: boolean;
            /** Stopped */
            stopped?: null;
        };
        /** FollowupCheck */
        FollowupCheck: {
            /** Project Id */
            project_id: number;
        };
        /** FollowupPreferences */
        FollowupPreferences: {
            /** Enabled */
            enabled: boolean;
        };
        /** FollowupRead */
        FollowupRead: {
            /** Id */
            id: number;
            /** Project Id */
            project_id: number;
            /**
             * Kind
             * @enum {string}
             */
            kind: "replan" | "needs_window" | "needs_plan" | "completed" | "needs_review";
            /** Title */
            title: string;
            /** Body */
            body: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "snoozed" | "applying" | "applied" | "resolved" | "dismissed" | "waiting";
            /** Version */
            version: number;
            /** Plan Id */
            plan_id: number | null;
            /** Snoozed Until */
            snoozed_until: string | null;
            /** Error */
            error: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Target Path */
            target_path: string;
            plan?: components["schemas"]["PlanRead"] | null;
        };
        /** FollowupResponse */
        FollowupResponse: {
            /** Version */
            version: number;
            /** Snooze Until */
            snooze_until?: string | null;
        };
        /** FollowupStatus */
        FollowupStatus: {
            /** Enabled */
            enabled: boolean;
            /** Autopilot Enabled */
            autopilot_enabled: boolean;
            /** Autonomy */
            autonomy: string;
            /** Last Scan */
            last_scan: {
                [key: string]: unknown;
            } | null;
        };
        /** FreeSlotOut */
        FreeSlotOut: {
            /** Start */
            start: string;
            /** End */
            end: string;
            /** Minutes */
            minutes: number;
        };
        /** GatherInput */
        GatherInput: {
            /** Queries */
            queries?: string[];
            /**
             * Max Sources
             * @default 3
             */
            max_sources?: number;
        };
        /** GatherResult */
        GatherResult: {
            /** Ok */
            ok: boolean;
            /** Project Id */
            project_id: number;
            /** Queries */
            queries: string[];
            /** Sources */
            sources: components["schemas"]["SourceRead"][];
            /** Errors */
            errors: {
                [key: string]: unknown;
            }[];
            /** Next Step */
            next_step: {
                [key: string]: unknown;
            };
            /** Source Boundary */
            source_boundary: string;
            /** Context */
            context: {
                [key: string]: unknown;
            };
        };
        /** GoalCreate */
        GoalCreate: {
            /** Title */
            title: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Start Date */
            start_date?: string | null;
            /** End Date */
            end_date?: string | null;
        };
        /** GoalOut */
        GoalOut: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Notes */
            notes: string;
            /** Status */
            status: string;
            /** Start Date */
            start_date?: string | null;
            /** End Date */
            end_date?: string | null;
            /** Key Results */
            key_results: components["schemas"]["KeyResultOut"][];
            /** Deleted At */
            deleted_at?: string | null;
        };
        /**
         * GoalProgressItemOut
         * @description progress 端点条目：自动类 KR 实时计算的 current_value + 0-100 整数进度。
         */
        GoalProgressItemOut: {
            /** Kr Id */
            kr_id: number;
            /** Title */
            title: string;
            /** Kind */
            kind: string;
            /** Target Value */
            target_value: number;
            /** Current Value */
            current_value: number;
            /** Unit */
            unit: string;
            /** Progress */
            progress: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HabitCreate */
        HabitCreate: {
            /** Name */
            name: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /**
             * Period
             * @default daily
             */
            period?: string;
            /**
             * Target Count
             * @default 1
             */
            target_count?: number;
            /**
             * Color
             * @default #22c55e
             */
            color?: string;
        };
        /** HabitLogOut */
        HabitLogOut: {
            /** Date */
            date: string;
            /** Count */
            count: number;
        };
        /** HabitOut */
        HabitOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Notes */
            notes: string;
            /** Period */
            period: string;
            /** Target Count */
            target_count: number;
            /** Color */
            color: string;
            status?: components["schemas"]["HabitStatusOut"] | null;
        };
        /**
         * HabitStatusOut
         * @description 实时状态（仅列表端点携带）：streak 今天未达标不打断（算到昨天）。
         */
        HabitStatusOut: {
            /** Today Count */
            today_count: number;
            /** Period Count */
            period_count: number;
            /** Streak */
            streak: number;
            /** Done Today */
            done_today: boolean;
        };
        /**
         * IcalImportOut
         * @description ICS 导入回包（re #048）：created=新建日程数。
         */
        IcalImportOut: {
            /** Created */
            created: number;
        };
        /** InboxPage */
        InboxPage: {
            /** Items */
            items: components["schemas"]["InboxRead"][];
            /** Total */
            total: number;
        };
        /** InboxRead */
        InboxRead: {
            /** Id */
            id: number;
            /** Source File Id */
            source_file_id: number | null;
            /** Source Name */
            source_name: string;
            /** Source Excerpt */
            source_excerpt: string;
            /** Item Key */
            item_key: string;
            /** Proposal */
            proposal: components["schemas"]["TaskProposal"] | components["schemas"]["EventProposal"] | components["schemas"]["LedgerProposal-Output"];
            /** Uncertainty */
            uncertainty: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "applied" | "rejected";
            /** Version */
            version: number;
            /** Target Id */
            target_id: number | null;
            /** Target State */
            target_state: ("active" | "deleted" | "missing") | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** JournalEntryOut */
        JournalEntryOut: {
            /** Id */
            id: number;
            /** Date */
            date: string;
            /** Content */
            content: string;
            /** Mood */
            mood?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** JournalUpsert */
        JournalUpsert: {
            /**
             * Content
             * @default
             */
            content?: string;
            /** Mood */
            mood?: string | null;
        };
        JsonValue: unknown;
        /** KeyResultCreate */
        KeyResultCreate: {
            /** Title */
            title: string;
            /**
             * Kind
             * @default manual
             */
            kind?: string;
            /**
             * Target Value
             * @default 100
             */
            target_value?: number;
            /**
             * Unit
             * @default
             */
            unit?: string;
            /**
             * Link
             * @default
             */
            link?: string;
        };
        /** KeyResultOut */
        KeyResultOut: {
            /** Id */
            id: number;
            /** Goal Id */
            goal_id: number;
            /** Title */
            title: string;
            /** Kind */
            kind: string;
            /** Target Value */
            target_value: number;
            /** Current Value */
            current_value: number;
            /** Unit */
            unit: string;
            /** Link */
            link: string;
        };
        /** LedgerDraft */
        "LedgerDraft-Input": {
            /**
             * Day
             * Format: date
             */
            day: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: number | string;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 未分类
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Source File Id */
            source_file_id?: null;
            /**
             * Source Excerpt
             * @default
             * @constant
             */
            source_excerpt?: "";
        };
        /** LedgerDraft */
        "LedgerDraft-Output": {
            /**
             * Day
             * Format: date
             */
            day: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "income" | "expense";
            /** Amount */
            amount: string;
            /**
             * Currency
             * @default CNY
             * @enum {string}
             */
            currency?: "CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY";
            /**
             * Category
             * @default 未分类
             */
            category?: string;
            /**
             * Account
             * @default 默认账户
             */
            account?: string;
            /**
             * Payee
             * @default
             */
            payee?: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Source File Id */
            source_file_id?: null;
            /**
             * Source Excerpt
             * @default
             * @constant
             */
            source_excerpt?: "";
        };
        /** LedgerProposal */
        "LedgerProposal-Input": {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "ledger";
            data: components["schemas"]["LedgerDraft-Input"];
        };
        /** LedgerProposal */
        "LedgerProposal-Output": {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "ledger";
            data: components["schemas"]["LedgerDraft-Output"];
        };
        /** LedgerSummary */
        LedgerSummary: {
            /**
             * Start
             * Format: date
             */
            start: string;
            /**
             * End
             * Format: date
             */
            end: string;
            /** Currencies */
            currencies: components["schemas"]["CurrencyTotal"][];
        };
        /** LinkCreate */
        LinkCreate: {
            /** Title */
            title: string;
            /** Url */
            url: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /**
             * Resource Type
             * @default link
             */
            resource_type?: string;
        };
        /** MCPEnableBody */
        MCPEnableBody: {
            /**
             * Enabled
             * @default true
             */
            enabled?: boolean;
        };
        /** MCPFetchBinding */
        MCPFetchBinding: {
            /** Server Id */
            server_id: number;
            /** Tool Name */
            tool_name: string;
            /**
             * Url Argument
             * @default url
             */
            url_argument?: string;
            /**
             * Url As List
             * @default false
             */
            url_as_list?: boolean;
            /**
             * Content Path
             * @default
             */
            content_path?: string;
        };
        /** MCPSearchBinding */
        MCPSearchBinding: {
            /** Server Id */
            server_id: number;
            /** Tool Name */
            tool_name: string;
            /**
             * Query Argument
             * @default query
             */
            query_argument?: string;
            /**
             * Limit Argument
             * @default max_results
             */
            limit_argument?: string | null;
            /**
             * Results Path
             * @default results
             */
            results_path?: string;
            /**
             * Title Field
             * @default title
             */
            title_field?: string;
            /**
             * Url Field
             * @default url
             */
            url_field?: string;
            /**
             * Description Field
             * @default content
             */
            description_field?: string;
        };
        /** MCPServerBody */
        MCPServerBody: {
            /** Name */
            name: string;
            /**
             * Transport
             * @default http
             */
            transport?: string;
            /**
             * Command
             * @default
             */
            command?: string;
            /**
             * Args Json
             * @default []
             */
            args_json?: string;
            /**
             * Env Json
             * @default {}
             */
            env_json?: string;
            /** Url */
            url?: string | null;
            /**
             * Headers Json
             * @default {}
             */
            headers_json?: string;
            /**
             * Timeout Sec
             * @default 30
             */
            timeout_sec?: number;
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
            /**
             * Auto Approve Readonly
             * @default false
             */
            auto_approve_readonly?: boolean;
            /**
             * Trusted
             * @default false
             */
            trusted?: boolean;
        };
        /**
         * MCPServerOut
         * @description MCP 服务器元数据（re #035）：敏感值 env/headers 不回显。
         */
        MCPServerOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Transport */
            transport: string;
            /** Command */
            command: string | null;
            /** Args Json */
            args_json: string;
            /** Url */
            url: string | null;
            /** Timeout Sec */
            timeout_sec: number;
            /** Enabled */
            enabled: boolean;
            /** Auto Approve Readonly */
            auto_approve_readonly: boolean;
            /** Trusted */
            trusted: boolean;
            /** Last Status */
            last_status: string;
            /** Last Error */
            last_error: string | null;
            /** Created At */
            created_at: string;
        };
        /**
         * MCPServerUpdate
         * @description 部分更新：仅落传出的字段。
         */
        MCPServerUpdate: {
            /** Name */
            name?: string | null;
            /** Transport */
            transport?: string | null;
            /** Command */
            command?: string | null;
            /** Args Json */
            args_json?: string | null;
            /** Env Json */
            env_json?: string | null;
            /** Url */
            url?: string | null;
            /** Headers Json */
            headers_json?: string | null;
            /** Timeout Sec */
            timeout_sec?: number | null;
            /** Enabled */
            enabled?: boolean | null;
            /** Auto Approve Readonly */
            auto_approve_readonly?: boolean | null;
            /** Trusted */
            trusted?: boolean | null;
        };
        /**
         * MCPTestOut
         * @description MCP 连通性测试回包（re #048）：成功/失败同形收敛；
         *     exclude_none 保证两路实形各键守恒（成功无 error、失败无 tools）。
         */
        MCPTestOut: {
            /** Ok */
            ok: boolean;
            /**
             * Tool Count
             * @default 0
             */
            tool_count?: number;
            /** Tools */
            tools?: components["schemas"]["MCPToolSummary"][] | null;
            /** Error */
            error?: string | null;
        };
        /**
         * MCPToolOut
         * @description MCP 工具清单项（re #048：/tools 直连查询实形）。
         */
        MCPToolOut: {
            /** Name */
            name: string;
            /** Description */
            description: string;
            /**
             * Input Schema
             * @default {}
             */
            input_schema?: {
                [key: string]: unknown;
            };
            /**
             * Read Only
             * @default false
             */
            read_only?: boolean;
        };
        /**
         * MCPToolSummary
         * @description 连通性测试回包里的工具摘要（实形只有 name/description，re #048）。
         */
        MCPToolSummary: {
            /** Name */
            name: string;
            /** Description */
            description: string;
        };
        /** MaterialHit */
        MaterialHit: {
            /** File Id */
            file_id: number;
            /** Name */
            name: string;
            /** Part */
            part: number;
            /** Location */
            location: string;
            /** Revision */
            revision: string;
            /** Excerpt */
            excerpt: string;
            /** Score */
            score: number;
            /** Next Call */
            next_call: {
                [key: string]: unknown;
            };
        };
        /** MaterialInput */
        MaterialInput: {
            /** File Id */
            file_id: number;
        };
        /** MaterialPart */
        MaterialPart: {
            /** Part */
            part: number;
            /** Location */
            location: string;
            /** Text */
            text: string;
            /** Citation */
            citation: string;
            /** Target Path */
            target_path: string;
        };
        /** MaterialRead */
        MaterialRead: {
            document: components["schemas"]["MaterialSummary"];
            /** Parts */
            parts: components["schemas"]["MaterialPart"][];
            /** Next Call */
            next_call: {
                [key: string]: unknown;
            } | null;
            /** Boundary */
            boundary: string;
        };
        /** MaterialSearch */
        MaterialSearch: {
            /** Query */
            query: string;
            /** Hits */
            hits: components["schemas"]["MaterialHit"][];
            /** Errors */
            errors: {
                [key: string]: unknown;
            }[];
            /** Documents */
            documents: components["schemas"]["MaterialSummary"][];
            /** Coverage */
            coverage: {
                [key: string]: unknown;
            };
            /** Next Call */
            next_call: {
                [key: string]: unknown;
            } | null;
            /** Boundary */
            boundary: string;
        };
        /** MaterialSummary */
        MaterialSummary: {
            /** File Id */
            file_id: number;
            /** Name */
            name: string;
            /** Revision */
            revision: string;
            /** Kind */
            kind: string;
            /** Total Parts */
            total_parts: number;
            /** Indexed Chars */
            indexed_chars: number;
            /** Partial */
            partial: boolean;
            /** Warnings */
            warnings: string[];
        };
        /**
         * MessageOut
         * @description 会话消息项（re #048）：display 为展示元数据对象（{"text": ...}）。
         */
        MessageOut: {
            /** Id */
            id: number;
            /** Role */
            role: string;
            /** Display */
            display: {
                [key: string]: unknown;
            };
            /** Created At */
            created_at: string;
        };
        /** ModelCatalogRequest */
        ModelCatalogRequest: {
            /** Config Id */
            config_id?: number | null;
            /**
             * Provider Kind
             * @default openai_compat
             * @enum {string}
             */
            provider_kind?: "openai_compat" | "openai_responses" | "anthropic";
            /** Base Url */
            base_url: string;
            /**
             * Api Key
             * Format: password
             */
            api_key?: string;
        };
        /** ModelCatalogResponse */
        ModelCatalogResponse: {
            /** Models */
            models: components["schemas"]["CatalogModel"][];
            /**
             * Truncated
             * @default false
             */
            truncated?: boolean;
        };
        /**
         * MonthDayOut
         * @description month 视图单日条目（re #020 事项3）：task_count=当日任务排期数；
         *     event_count=当日独立日程 RRULE 展开计数（双周课隔周 +1）。
         */
        MonthDayOut: {
            /** Date */
            date: string;
            /** Task Count */
            task_count: number;
            /**
             * Event Count
             * @default 0
             */
            event_count?: number;
        };
        /**
         * NotificationOut
         * @description 通知实形（re #047：前端 Notification 手写收敛依据）。task_id/read_at 可空，
         *     read_at 为 null 即未读；remind_at/read_at 序列化为 ISO 串（与既有回包一致）。
         */
        NotificationOut: {
            /** Id */
            id: number;
            /** Task Id */
            task_id?: number | null;
            /** Kind */
            kind: string;
            /** Title */
            title: string;
            /** Body */
            body: string;
            /**
             * Remind At
             * Format: date-time
             */
            remind_at: string;
            /** Read At */
            read_at?: string | null;
            /** Target Path */
            target_path?: string | null;
        };
        /** OkOut */
        OkOut: {
            /** Ok */
            ok: boolean;
        };
        /** PlanDraft */
        PlanDraft: {
            /** Version */
            version: number;
            /** Rationale */
            rationale: string;
            /**
             * Steps
             * @description 按先后顺序列步骤；不提供时间点或模型生成的任务编号。程序负责排程。
             */
            steps: components["schemas"]["StepDraft"][];
        };
        /** PlanHistory */
        PlanHistory: {
            /** Items */
            items: components["schemas"]["PlanSummary"][];
            /** Next Before */
            next_before?: number | null;
        };
        /** PlanRead */
        PlanRead: {
            /** Id */
            id: number;
            /** Project Id */
            project_id: number;
            /** Project Version */
            project_version: number;
            /**
             * Kind
             * @enum {string}
             */
            kind: "initial" | "replan" | "extension" | "revision";
            /**
             * State
             * @enum {string}
             */
            state: "draft" | "applied";
            /** Rationale */
            rationale: string;
            /** Units */
            units: components["schemas"]["UnitRead"][];
            /** Assignments */
            assignments: components["schemas"]["Assignment"][];
            /** Unassigned */
            unassigned: components["schemas"]["Unassigned"][];
            /** Preserved */
            preserved: {
                [key: string]: unknown;
            }[];
            /** Result */
            result: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Applied At */
            applied_at: string | null;
            /** Feedback Ids */
            feedback_ids?: number[];
            revision?: components["schemas"]["RevisionRead"] | null;
        };
        /**
         * PlanRejectOut
         * @description 计划拒绝：无可续跑流，不提供 resume（re #016 minor）。
         */
        PlanRejectOut: {
            /**
             * Ok
             * @default true
             */
            ok?: boolean;
        };
        /** PlanSummary */
        PlanSummary: {
            /** Id */
            id: number;
            /** Kind */
            kind: string;
            /** State */
            state: string;
            /** Rationale */
            rationale: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Applied At */
            applied_at: string | null;
        };
        /** ProjectCreate */
        ProjectCreate: {
            /**
             * Title
             * @description 主题或学习项目名称；联网默认只搜索此主题。
             */
            title: string;
            /**
             * Objective
             * @description 希望学会什么或最终产出什么；保留用户原始目标。
             */
            objective: string;
            /**
             * Kind
             * @default study
             * @enum {string}
             */
            kind?: "study" | "research";
            /**
             * Background
             * @description 现有基础与约束；未提供时留空，不捏造水平。
             * @default
             */
            background?: string;
            /**
             * Start Date
             * Format: date
             */
            start_date?: string;
            /**
             * End Date
             * @description 留空时先以起始日后两周为规划窗口，界面明确展示此假设。
             */
            end_date?: string | null;
            /**
             * Daily Minutes
             * @default 60
             */
            daily_minutes?: number;
            /**
             * Session Minutes
             * @default 45
             */
            session_minutes?: number;
            /**
             * Weekdays
             * @description 可安排日期，0=周一，6=周日。
             */
            weekdays?: number[];
            /** Window Start */
            window_start?: string | null;
            /** Window End */
            window_end?: string | null;
            /** Request Key */
            request_key?: string | null;
        };
        /** ProjectDetail */
        ProjectDetail: {
            project: components["schemas"]["ProjectRead"];
            /** Sources */
            sources: components["schemas"]["SourceRead"][];
            /** Tasks */
            tasks: components["schemas"]["ProjectTaskRead"][];
            latest_plan: components["schemas"]["PlanRead"] | null;
            /** Next Step */
            next_step: {
                [key: string]: unknown;
            };
            feedback?: components["schemas"]["FeedbackPage"];
            /** Revision Targets */
            revision_targets?: components["schemas"]["RevisionTarget"][];
        };
        /** ProjectRead */
        ProjectRead: {
            /** Id */
            id: number;
            spec: components["schemas"]["ProjectSpec"];
            /** Version */
            version: number;
            /** Assumptions */
            assumptions: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "archived";
            /** Goal Id */
            goal_id: number | null;
            /** Verified Sources */
            verified_sources: number;
            /** Total Sources */
            total_sources: number;
            /** Total Tasks */
            total_tasks: number;
            /** Completed Tasks */
            completed_tasks: number;
            /** Missing Tasks */
            missing_tasks: number;
            /** Latest Plan Id */
            latest_plan_id: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** ProjectSlotRead */
        ProjectSlotRead: {
            /** Id */
            id: number;
            /** Date */
            date: string;
            /** Start */
            start: string | null;
            /** End */
            end: string | null;
        };
        /** ProjectSpec */
        ProjectSpec: {
            /**
             * Title
             * @description 主题或学习项目名称；联网默认只搜索此主题。
             */
            title: string;
            /**
             * Objective
             * @description 希望学会什么或最终产出什么；保留用户原始目标。
             */
            objective: string;
            /**
             * Kind
             * @default study
             * @enum {string}
             */
            kind?: "study" | "research";
            /**
             * Background
             * @description 现有基础与约束；未提供时留空，不捏造水平。
             * @default
             */
            background?: string;
            /**
             * Start Date
             * Format: date
             */
            start_date?: string;
            /**
             * End Date
             * @description 留空时先以起始日后两周为规划窗口，界面明确展示此假设。
             */
            end_date?: string | null;
            /**
             * Daily Minutes
             * @default 60
             */
            daily_minutes?: number;
            /**
             * Session Minutes
             * @default 45
             */
            session_minutes?: number;
            /**
             * Weekdays
             * @description 可安排日期，0=周一，6=周日。
             */
            weekdays?: number[];
            /** Window Start */
            window_start?: string | null;
            /** Window End */
            window_end?: string | null;
        };
        /** ProjectTaskRead */
        ProjectTaskRead: {
            /** Id */
            id: number;
            /** Task Id */
            task_id: number | null;
            /** Title */
            title: string;
            /** Status */
            status: string;
            /** Minutes */
            minutes: number | null;
            /** Notes */
            notes: string;
            /** Source Ids */
            source_ids: number[];
            /** Source Refs */
            source_refs?: components["schemas"]["SourceReference"][];
            /** Slots */
            slots: components["schemas"]["ProjectSlotRead"][];
        };
        /** ProjectUpdate */
        ProjectUpdate: {
            /** Version */
            version: number;
            spec: components["schemas"]["ProjectSpec"];
        };
        /**
         * RangeDayLoad
         * @description range 是任务负载视图（不含独立日程）：日期键 → 当日排期明细与预估总时长。
         */
        RangeDayLoad: {
            /** Items */
            items: components["schemas"]["RangeTaskItem"][];
            /** Estimated Minutes */
            estimated_minutes: number;
        };
        /** RangeTaskItem */
        RangeTaskItem: {
            /** Task Id */
            task_id: number;
            /** Title */
            title: string;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Estimated Minutes */
            estimated_minutes?: number | null;
        };
        /** ReportBody */
        ReportBody: {
            /** Target Date */
            target_date?: string | null;
        };
        /**
         * ReportOut
         * @description 报告实形（re #047：前端 Report 手写类型收敛依据）。
         *     period_start/end 为 ISO 日期串、created_at 为 ISO 时间串——与 _out() 既有回包一致。
         */
        ReportOut: {
            /** Id */
            id: number;
            /** Report Type */
            report_type: string;
            /** Period Start */
            period_start: string;
            /** Period End */
            period_end: string;
            /** Title */
            title: string;
            /** Content */
            content: string;
            /** Model Name */
            model_name: string;
            /** Created At */
            created_at: string;
        };
        /**
         * ResumeBlockedOut
         * @description resume 拒绝体（re #020 k3 major）：本轮仍有未决审批卡。
         *     前端按 pending 清单提示用户逐张批准/拒绝后再续跑。
         *     re #023④：consumed=true 表示该轮审批批次已被 resume 消费（confirmed 已转
         *     executed，源 run 已记 resumed_by_runs）——重复 resume 幂等拒绝，不会重复回填。
         */
        ResumeBlockedOut: {
            /** Pending */
            pending: components["schemas"]["ResumeBlockedPending"][];
            /**
             * Consumed
             * @default false
             */
            consumed?: boolean;
            /**
             * Message
             * @default
             */
            message?: string;
        };
        /**
         * ResumeBlockedPending
         * @description 一条未决审批卡的定位信息。
         */
        ResumeBlockedPending: {
            /** Action Id */
            action_id: number;
            /** Tool Name */
            tool_name: string;
        };
        /** Revision */
        Revision: {
            /** Version */
            version: number;
            /** Proposal */
            proposal: components["schemas"]["TaskProposal"] | components["schemas"]["EventProposal"] | components["schemas"]["LedgerProposal-Input"];
            /**
             * Uncertainty
             * @default
             */
            uncertainty?: string;
        };
        /** RevisionDraft */
        RevisionDraft: {
            /** Version */
            version: number;
            /** Rationale */
            rationale: string;
            /**
             * Steps
             * @description 按先后顺序列步骤；不提供时间点或模型生成的任务编号。程序负责排程。
             */
            steps: components["schemas"]["StepDraft"][];
            /**
             * Feedback Ids
             * @description 本方案回应的真实反馈编号；不填写即为独立追加阶段。
             */
            feedback_ids?: number[];
            /**
             * Mode
             * @enum {string}
             */
            mode: "insert_before" | "replace";
            /**
             * Target Link Id
             * @description 目标项目任务记录编号，来自tasks[].id，不是task_id。
             */
            target_link_id: number;
            /**
             * Movable Task Link Ids
             * @description 仅用户明确允许移动的手工安排对应tasks[].id。默认保留手工安排；不允许移动进行中事项。
             */
            movable_task_link_ids?: number[];
        };
        /** RevisionRead */
        RevisionRead: {
            /**
             * Mode
             * @enum {string}
             */
            mode: "insert_before" | "replace";
            /** Target Link Id */
            target_link_id: number;
            before_task: components["schemas"]["ProjectTaskRead"];
            /** Moved Manual */
            moved_manual?: {
                [key: string]: unknown;
            }[];
            /** New Unit Indices */
            new_unit_indices: number[];
            /** Warnings */
            warnings?: string[];
        };
        /** RevisionTarget */
        RevisionTarget: {
            /** Task Link Id */
            task_link_id: number;
            /** Title */
            title: string;
            /** Can Insert Before */
            can_insert_before: boolean;
            /** Can Replace */
            can_replace: boolean;
            /** Can Move */
            can_move: boolean;
            /** Manual Schedule */
            manual_schedule: boolean;
            /** Reason */
            reason: string;
        };
        /**
         * RiskItem
         * @description 逾期风险分条目（risk 序列项，score 降序；规则分见 risk()）。
         */
        RiskItem: {
            /** Task Id */
            task_id: number;
            /** Title */
            title: string;
            /** Score */
            score: number;
            /** Due Date */
            due_date?: string | null;
        };
        /** ScheduleEntryCreate */
        ScheduleEntryCreate: {
            /** Task Id */
            task_id: number;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /**
             * Source
             * @default manual
             */
            source?: string;
            /**
             * Note
             * @default
             */
            note?: string;
        };
        /**
         * ScheduleEntryOut
         * @description 排期条目本体（re #B5）：列表/创建/更新端点共用同一形状。
         */
        ScheduleEntryOut: {
            /** Id */
            id: number;
            /** Task Id */
            task_id: number;
            /** Date */
            date: string;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Source */
            source: string;
            /** Note */
            note: string;
        };
        /** ScheduleEntryUpdate */
        ScheduleEntryUpdate: {
            /** Date */
            date?: string | null;
            /** Start Time */
            start_time?: string | null;
            /** End Time */
            end_time?: string | null;
            /** Note */
            note?: string | null;
        };
        /** SearchBody */
        SearchBody: {
            /** Query */
            query: string;
            /**
             * Max Results
             * @default 5
             */
            max_results?: number;
            /** Provider */
            provider?: ("builtin" | "tavily" | "mcp") | null;
        };
        /** SearchError */
        SearchError: {
            /** Error */
            error: string;
        };
        /** SearchHit */
        SearchHit: {
            /** Title */
            title: string;
            /** Url */
            url: string;
            /** Description */
            description: string;
        };
        /** SkillBody */
        SkillBody: {
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /**
             * Content
             * @default
             */
            content?: string;
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
        };
        /**
         * SkillOut
         * @description AI 技能列表项（re #047：前端 SkillInfo 手写收敛依据）。
         */
        SkillOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Enabled */
            enabled: boolean;
            /** Is Builtin */
            is_builtin: boolean;
        };
        /** SourceRead */
        SourceRead: {
            /** Id */
            id: number;
            /**
             * Kind
             * @enum {string}
             */
            kind: "web" | "file";
            /** Title */
            title: string;
            /** Url */
            url: string;
            /** Query */
            query: string;
            /** Description */
            description: string;
            /** Content */
            content: string;
            /**
             * Status
             * @enum {string}
             */
            status: "candidate" | "verified" | "failed";
            /** Error */
            error: string;
            /** Library File Id */
            library_file_id: number | null;
            /**
             * Library State
             * @enum {string}
             */
            library_state: "active" | "deleted" | "missing";
            /** Retrieved At */
            retrieved_at: string | null;
            /** Superseded By */
            superseded_by?: number | null;
            /**
             * Content Is Excerpt
             * @default true
             */
            content_is_excerpt?: boolean;
            document?: components["schemas"]["MaterialSummary"] | null;
            /** Read Call */
            read_call?: {
                [key: string]: unknown;
            } | null;
        };
        /** SourceReference */
        SourceReference: {
            /** Source Id */
            source_id: number;
            /** Part */
            part: number;
            /** Revision */
            revision: string;
            /** Quote */
            quote: string;
        };
        /**
         * StatsDailyPoint
         * @description 单日完成/新建计数（daily 序列项，date 为 YYYY-MM-DD）。
         */
        StatsDailyPoint: {
            /** Date */
            date: string;
            /** Completed */
            completed: number;
            /** Created */
            created: number;
        };
        /**
         * StatsPriorityItem
         * @description 按优先级聚合（by-priority 序列项，fixed high/medium/low）。
         */
        StatsPriorityItem: {
            /** Priority */
            priority: string;
            /** Todo */
            todo: number;
            /** Doing */
            doing: number;
            /** Done */
            done: number;
        };
        /**
         * StatsSummary
         * @description 任务面汇总计数。
         */
        StatsSummary: {
            /** Todo */
            todo: number;
            /** Doing */
            doing: number;
            /** Done */
            done: number;
            /** Overdue */
            overdue: number;
            /** Due Today */
            due_today: number;
            /** Due 7D */
            due_7d: number;
        };
        /**
         * StatsTagItem
         * @description 按标签聚合（by-tag 序列项，按 total 降序）。
         */
        StatsTagItem: {
            /** Tag */
            tag: string;
            /** Total */
            total: number;
            /** Done */
            done: number;
        };
        /** StepDraft */
        StepDraft: {
            /** Title */
            title: string;
            /**
             * Outcome
             * @description 本步完成后可检查的产出或掌握标准。
             */
            outcome: string;
            /**
             * Minutes
             * @description 估计总投入分钟；程序自动拆成单次学习时段。
             */
            minutes: number;
            /**
             * Source Ids
             * @description 本项目已抓取正文的资料编号；只能引用返回的真实编号。
             */
            source_ids?: number[];
            /**
             * Source Refs
             * @description 可选精确出处：source_id为项目资料编号，part/revision/quote来自read_material原文，不猜页码。
             */
            source_refs?: components["schemas"]["SourceReference"][];
        };
        /**
         * SubtaskRead
         * @description 子任务读取面（re #B4）：随 TaskRead 内嵌返回，REST 消费者可渲染子任务清单。
         */
        SubtaskRead: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Done */
            done: boolean;
            /** Estimated Minutes */
            estimated_minutes: number | null;
            /** Completed At */
            completed_at: string | null;
        };
        /**
         * SubtaskWriteOut
         * @description 子任务写端点响应（re #033）：SubtaskRead + task_id（写返回历来带归属，载荷守恒）。
         */
        SubtaskWriteOut: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Done */
            done: boolean;
            /** Estimated Minutes */
            estimated_minutes: number | null;
            /** Completed At */
            completed_at: string | null;
            /** Task Id */
            task_id: number;
        };
        /**
         * TagOut
         * @description 标签项（re #048：GET /api/tasks/tags 实形）。
         */
        TagOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Color */
            color: string;
        };
        /** TaskCreate */
        TaskCreate: {
            /** Title */
            title: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Due Date */
            due_date?: string | null;
            /** Due Time */
            due_time?: string | null;
            /** Remind Offsets */
            remind_offsets?: number[];
            /**
             * Priority
             * @default medium
             */
            priority?: string;
            /**
             * Status
             * @default todo
             */
            status?: string;
            /** Start Date */
            start_date?: string | null;
            /**
             * Recur Rule
             * @default none
             */
            recur_rule?: string;
            /**
             * Recur Interval
             * @default 1
             */
            recur_interval?: number;
            /** Recur Rrule */
            recur_rrule?: string | null;
            /** Estimated Minutes */
            estimated_minutes?: number | null;
            /** Tag Names */
            tag_names?: string[];
        };
        /** TaskDraft */
        TaskDraft: {
            /** Title */
            title: string;
            /**
             * Notes
             * @default
             */
            notes?: string;
            /** Due Date */
            due_date?: string | null;
            /** Due Time */
            due_time?: string | null;
            /** Remind Offsets */
            remind_offsets?: number[];
            /**
             * Priority
             * @default medium
             * @enum {string}
             */
            priority?: "high" | "medium" | "low";
            /**
             * Status
             * @default todo
             * @constant
             */
            status?: "todo";
            /** Start Date */
            start_date?: string | null;
            /**
             * Recur Rule
             * @default none
             * @enum {string}
             */
            recur_rule?: "none" | "daily" | "weekdays" | "weekly" | "monthly";
            /**
             * Recur Interval
             * @default 1
             */
            recur_interval?: number;
            /** Recur Rrule */
            recur_rrule?: string | null;
            /** Estimated Minutes */
            estimated_minutes?: number | null;
            /** Tag Names */
            tag_names?: string[];
        };
        /** TaskProposal */
        TaskProposal: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "task";
            data: components["schemas"]["TaskDraft"];
        };
        /** TaskRead */
        TaskRead: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Notes */
            notes: string;
            /** Due Date */
            due_date: string | null;
            /** Due Time */
            due_time: string | null;
            /** Remind Offsets */
            remind_offsets: number[];
            /** Priority */
            priority: string;
            /** Status */
            status: string;
            /** Progress */
            progress: number;
            /** Start Date */
            start_date: string | null;
            /** Recur Rule */
            recur_rule: string;
            /** Recur Interval */
            recur_interval: number;
            /** Recur Rrule */
            recur_rrule: string | null;
            /** Estimated Minutes */
            estimated_minutes: number | null;
            /** Tags */
            tags: string[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Completed At */
            completed_at: string | null;
            /**
             * Subtasks
             * @default []
             */
            subtasks?: components["schemas"]["SubtaskRead"][];
        };
        /** TaskUpdate */
        TaskUpdate: {
            /** Title */
            title?: string | null;
            /** Notes */
            notes?: string | null;
            /** Due Date */
            due_date?: string | null;
            /** Due Time */
            due_time?: string | null;
            /** Remind Offsets */
            remind_offsets?: number[] | null;
            /** Priority */
            priority?: string | null;
            /** Status */
            status?: string | null;
            /** Start Date */
            start_date?: string | null;
            /** Recur Rule */
            recur_rule?: string | null;
            /** Recur Interval */
            recur_interval?: number | null;
            /** Recur Rrule */
            recur_rrule?: string | null;
            /** Estimated Minutes */
            estimated_minutes?: number | null;
            /** Tag Names */
            tag_names?: string[] | null;
        };
        /** TimeLogOut */
        TimeLogOut: {
            /** Id */
            id: number;
            /** Task Id */
            task_id?: number | null;
            /** Task Title */
            task_title: string;
            /** Kind */
            kind: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Ended At */
            ended_at?: string | null;
            /** Minutes */
            minutes: number;
        };
        /** TimerStart */
        TimerStart: {
            /** Task Id */
            task_id?: number | null;
            /**
             * Task Title
             * @default
             */
            task_title?: string;
            /**
             * Kind
             * @default focus
             */
            kind?: string;
        };
        /**
         * ToolGrantOut
         * @description 「始终允许」规则（re #019：可审计、可撤销）。
         */
        ToolGrantOut: {
            /** Id */
            id: number;
            /** Tool Name */
            tool_name: string;
            /** Arg Pattern */
            arg_pattern: string;
            /** Created At */
            created_at: string;
        };
        /** Unassigned */
        Unassigned: {
            /** Unit Index */
            unit_index: number;
            /** Reason */
            reason: string;
        };
        /**
         * UncheckBody
         * @description re #B3：date 可省略（缺省=今天），与 check_in 的 day=None 语义一致。
         */
        UncheckBody: {
            /** Date */
            date?: string | null;
        };
        /** UncheckOut */
        UncheckOut: {
            /** Ok */
            ok: boolean;
        };
        /** UnitRead */
        UnitRead: {
            /** Title */
            title: string;
            /** Outcome */
            outcome: string;
            /** Minutes */
            minutes: number;
            /** Source Ids */
            source_ids: number[];
            /** Source Refs */
            source_refs?: components["schemas"]["SourceReference"][];
            /** Existing Task Id */
            existing_task_id?: number | null;
            /** Not Before */
            not_before?: string | null;
            /** Blocked By */
            blocked_by?: number | null;
            /** Not After */
            not_after?: string | null;
            /**
             * Replace Content
             * @default false
             */
            replace_content?: boolean;
        };
        /**
         * UnreadOut
         * @description 未读数（前端 30s 轮询依据）。
         */
        UnreadOut: {
            /** Count */
            count: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** VersionInput */
        VersionInput: {
            /** Version */
            version: number;
        };
        /**
         * VisionConfig
         * @description Saving enabled=True explicitly opts into automatic, readonly vision use.
         */
        VisionConfig: {
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
            /** Server Id */
            server_id?: number | null;
            /**
             * Tool Name
             * @default
             */
            tool_name?: string;
            /** Arguments */
            arguments?: {
                [key: string]: components["schemas"]["JsonValue"];
            };
        };
        /** WatchConfig */
        WatchConfig: {
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
            /** Queries */
            queries?: string[];
            /**
             * Frequency
             * @default weekly
             * @enum {string}
             */
            frequency?: "daily" | "weekly";
            /**
             * Weekday
             * @default 0
             */
            weekday?: number;
            /**
             * Time
             * @default 09:00
             */
            time?: string;
            /**
             * Max Sources
             * @default 3
             */
            max_sources?: number;
            /**
             * Refresh Existing
             * @default true
             */
            refresh_existing?: boolean;
        };
        /** WatchRead */
        WatchRead: {
            /** Project Id */
            project_id: number;
            /** Version */
            version: number;
            config: components["schemas"]["WatchConfig"];
            /** Next Run At */
            next_run_at: string | null;
            /** Running */
            running: boolean;
            /** Project Active */
            project_active: boolean;
            /** Runs */
            runs: components["schemas"]["WatchRunRead"][];
            /** Next Before */
            next_before: number | null;
        };
        /** WatchRunRead */
        WatchRunRead: {
            /** Id */
            id: number;
            /** Project Id */
            project_id: number;
            /** Status */
            status: string;
            config: components["schemas"]["WatchConfig"];
            /** Sources */
            sources: components["schemas"]["WatchSource"][];
            /** Errors */
            errors: string[];
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Finished At */
            finished_at: string | null;
        };
        /** WatchSource */
        WatchSource: {
            /** Source Id */
            source_id: number;
            /** Library File Id */
            library_file_id?: number | null;
            /** Title */
            title: string;
            /** Url */
            url: string;
            /** Changed */
            changed: boolean;
            /** Status */
            status: string;
            /**
             * Error
             * @default
             */
            error?: string;
        };
        /** WatchUpdate */
        WatchUpdate: {
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
            /** Queries */
            queries?: string[];
            /**
             * Frequency
             * @default weekly
             * @enum {string}
             */
            frequency?: "daily" | "weekly";
            /**
             * Weekday
             * @default 0
             */
            weekday?: number;
            /**
             * Time
             * @default 09:00
             */
            time?: string;
            /**
             * Max Sources
             * @default 3
             */
            max_sources?: number;
            /**
             * Refresh Existing
             * @default true
             */
            refresh_existing?: boolean;
            /** Version */
            version: number;
        };
        /** WebServicesConfig */
        WebServicesConfig: {
            /**
             * Search Provider
             * @default builtin
             * @enum {string}
             */
            search_provider?: "builtin" | "tavily" | "mcp";
            /**
             * Fetch Provider
             * @default builtin
             * @enum {string}
             */
            fetch_provider?: "builtin" | "tavily" | "mcp";
            /**
             * Tavily Search Depth
             * @default basic
             * @enum {string}
             */
            tavily_search_depth?: "basic" | "advanced";
            /**
             * Tavily Extract Depth
             * @default basic
             * @enum {string}
             */
            tavily_extract_depth?: "basic" | "advanced";
            mcp_search?: components["schemas"]["MCPSearchBinding"] | null;
            mcp_fetch?: components["schemas"]["MCPFetchBinding"] | null;
        };
        /** WebServicesOut */
        WebServicesOut: {
            config: components["schemas"]["WebServicesConfig"];
            /** Tavily Has Api Key */
            tavily_has_api_key: boolean;
        };
        /** WorkspaceOut */
        WorkspaceOut: {
            /**
             * Revision
             * @default 0
             */
            revision?: number;
            state?: components["schemas"]["WorkspaceState"];
        };
        /** WorkspaceState */
        WorkspaceState: {
            /** Active Id */
            active_id?: number | null;
            /**
             * Drafts
             * @default {}
             */
            drafts?: {
                [key: string]: components["schemas"]["Draft"];
            };
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
    list_tasks_api_tasks_get: {
        parameters: {
            query?: {
                q?: string | null;
                status?: string | null;
                priority?: string | null;
                tag?: string | null;
                due_before?: string | null;
                due_after?: string | null;
            };
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
                    "application/json": components["schemas"]["TaskRead"][];
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
    create_task_api_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskRead"];
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
    list_trash_api_tasks_trash_get: {
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
                    "application/json": components["schemas"]["TaskRead"][];
                };
            };
        };
    };
    list_tags_api_tasks_tags_get: {
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
                    "application/json": components["schemas"]["TagOut"][];
                };
            };
        };
    };
    get_task_api_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
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
                    "application/json": components["schemas"]["TaskRead"];
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
    delete_task_api_tasks__task_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_task_api_tasks__task_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskRead"];
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
    restore_task_api_tasks__task_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
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
                    "application/json": components["schemas"]["TaskRead"];
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
    purge_task_api_tasks__task_id__purge_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    create_subtask_api_tasks__task_id__subtasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubtaskWriteOut"];
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
    delete_subtask_api_tasks__task_id__subtasks__subtask_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
                subtask_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_subtask_api_tasks__task_id__subtasks__subtask_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
                subtask_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubtaskWriteOut"];
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
    list_entries_api_schedule_entries_get: {
        parameters: {
            query?: {
                task_id?: number | null;
                date_from?: string | null;
                date_to?: string | null;
            };
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
                    "application/json": components["schemas"]["ScheduleEntryOut"][];
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
    create_entry_api_schedule_entries_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScheduleEntryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScheduleEntryOut"];
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
    delete_entry_api_schedule_entries__entry_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_entry_api_schedule_entries__entry_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScheduleEntryUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScheduleEntryOut"];
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
    day_view_api_schedule_day_get: {
        parameters: {
            query: {
                date: string;
            };
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
                    "application/json": components["schemas"]["DayViewOut"];
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
    month_view_api_schedule_month_get: {
        parameters: {
            query: {
                year: number;
                month: number;
            };
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
                    "application/json": components["schemas"]["MonthDayOut"][];
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
    range_view_api_schedule_range_get: {
        parameters: {
            query: {
                start: string;
                days?: number;
            };
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
                    "application/json": {
                        [key: string]: components["schemas"]["RangeDayLoad"];
                    };
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
    create_event_api_schedule_events_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventDetailOut"];
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
    expand_events_api_schedule_events_expand_get: {
        parameters: {
            query: {
                start: string;
                end: string;
            };
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
                    "application/json": components["schemas"]["ExpandedEventOut"][];
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
    get_event_api_schedule_events__event_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                event_id: number;
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
                    "application/json": components["schemas"]["EventDetailOut"];
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
    delete_event_api_schedule_events__event_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                event_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_event_api_schedule_events__event_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                event_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventDetailOut"];
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
    find_conflicts_api_schedule_conflicts_get: {
        parameters: {
            query: {
                start: string;
                end: string;
            };
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
                    "application/json": components["schemas"]["ConflictOut"][];
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
    free_slots_api_schedule_free_slots_get: {
        parameters: {
            query: {
                date: string;
                min_minutes?: number;
            };
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
                    "application/json": components["schemas"]["FreeSlotOut"][];
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
    list_goals_api_goals_get: {
        parameters: {
            query?: {
                /** @description 包含已删除（回收站）目标 */
                include_deleted?: boolean;
                /**
                 * @deprecated
                 * @description 旧参数名（re #B2 改名），等价 include_deleted，兼容保留
                 */
                include_archived?: boolean | null;
            };
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
                    "application/json": components["schemas"]["GoalOut"][];
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
    create_goal_api_goals_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GoalCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalOut"];
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
    list_trash_api_goals_trash_get: {
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
                    "application/json": components["schemas"]["GoalOut"][];
                };
            };
        };
    };
    get_goal_api_goals__goal_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
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
                    "application/json": components["schemas"]["GoalOut"];
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
    delete_goal_api_goals__goal_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_goal_api_goals__goal_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalOut"];
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
    restore_goal_api_goals__goal_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
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
                    "application/json": components["schemas"]["GoalOut"];
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
    purge_goal_api_goals__goal_id__purge_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    add_key_result_api_goals__goal_id__key_results_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KeyResultCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KeyResultOut"];
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
    delete_key_result_api_goals_key_results__kr_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kr_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_key_result_api_goals_key_results__kr_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kr_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KeyResultOut"];
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
    goal_progress_api_goals__goal_id__progress_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
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
                    "application/json": components["schemas"]["GoalProgressItemOut"][];
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
    list_habits_api_habits_get: {
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
                    "application/json": components["schemas"]["HabitOut"][];
                };
            };
        };
    };
    create_habit_api_habits_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HabitCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HabitOut"];
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
    check_in_api_habits__habit_id__check_in_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                habit_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                } | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckInOut"];
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
    uncheck_api_habits__habit_id__uncheck_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                habit_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["UncheckBody"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UncheckOut"];
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
    list_logs_api_habits__habit_id__logs_get: {
        parameters: {
            query?: {
                days?: number;
            };
            header?: never;
            path: {
                habit_id: number;
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
                    "application/json": components["schemas"]["HabitLogOut"][];
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
    delete_habit_api_habits__habit_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                habit_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    today_entry_api_journal_today_get: {
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
                    "application/json": components["schemas"]["JournalEntryOut"] | null;
                };
            };
        };
    };
    list_entries_api_journal_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["JournalEntryOut"][];
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
    get_entry_api_journal__day__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day: string;
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
                    "application/json": components["schemas"]["JournalEntryOut"] | null;
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
    upsert_entry_api_journal__day__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JournalUpsert"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalEntryOut"];
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
    delete_entry_api_journal__day__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                day: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    start_api_focus_start_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TimerStart"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimeLogOut"];
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
    stop_api_focus_stop_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                } | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimeLogOut"] | components["schemas"]["FocusStopMissOut"];
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
    current_api_focus_current_get: {
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
                    "application/json": components["schemas"]["TimeLogOut"] | null;
                };
            };
        };
    };
    logs_api_focus_logs_get: {
        parameters: {
            query?: {
                days?: number;
                task_id?: number | null;
            };
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
                    "application/json": components["schemas"]["TimeLogOut"][];
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
    stats_api_focus_stats_get: {
        parameters: {
            query?: {
                days?: number;
            };
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
                    "application/json": components["schemas"]["FocusStatsOut"];
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
    delete_log_api_focus_logs__log_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                log_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_files_api_files_get: {
        parameters: {
            query?: {
                q?: string | null;
            };
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
                    "application/json": components["schemas"]["FileOut"][];
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
    upload_api_files_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_api_files_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileOut"];
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
    create_link_api_files_links_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LinkCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileOut"];
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
    list_trash_api_files_trash_get: {
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
                    "application/json": components["schemas"]["FileOut"][];
                };
            };
        };
    };
    task_files_api_files_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: number;
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
                    "application/json": components["schemas"]["FileOut"][];
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
    get_file_api_files__file_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
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
                    "application/json": components["schemas"]["FileOut"];
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
    soft_delete_api_files__file_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    update_notes_api_files__file_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileOut"];
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
    restore_api_files__file_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
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
                    "application/json": components["schemas"]["FileOut"];
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
    purge_api_files__file_id__purge_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    attach_api_files__file_id__attach__task_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
                task_id: number;
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
                    "application/json": components["schemas"]["OkOut"];
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
    detach_api_files__file_id__detach__task_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: number;
                task_id: number;
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
                    "application/json": components["schemas"]["OkOut"];
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
    list_notifications_api_notifications_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["NotificationOut"][];
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
    unread_api_notifications_unread_get: {
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
                    "application/json": components["schemas"]["UnreadOut"];
                };
            };
        };
    };
    mark_read_api_notifications__notification_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notification_id: number;
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
                    "application/json": components["schemas"]["EnableOut"];
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
    mark_all_read_api_notifications_read_all_post: {
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
                    "application/json": components["schemas"]["EnableOut"];
                };
            };
        };
    };
    summary_api_stats_summary_get: {
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
                    "application/json": components["schemas"]["StatsSummary"];
                };
            };
        };
    };
    daily_api_stats_daily_get: {
        parameters: {
            query?: {
                days?: number;
            };
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
                    "application/json": components["schemas"]["StatsDailyPoint"][];
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
    by_tag_api_stats_by_tag_get: {
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
                    "application/json": components["schemas"]["StatsTagItem"][];
                };
            };
        };
    };
    by_priority_api_stats_by_priority_get: {
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
                    "application/json": components["schemas"]["StatsPriorityItem"][];
                };
            };
        };
    };
    risk_api_stats_risk_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["RiskItem"][];
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
    get_settings_api_settings_get: {
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
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    put_settings_api_settings_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
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
    export_api_ical_export_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description ICS 日历文本（text/calendar） */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/calendar": string;
                };
            };
        };
    };
    import_ics_api_ical_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_import_ics_api_ical_import_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IcalImportOut"];
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
    upload_attachment_ai_attachments_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_attachment_ai_attachments_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttachmentOut"];
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
    chat_stream_ai_chat_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
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
    list_conversations_ai_conversations_get: {
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
                    "application/json": components["schemas"]["ConversationOut"][];
                };
            };
        };
    };
    conversation_detail_ai_conversations__cid__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
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
                    "application/json": components["schemas"]["MessageOut"][];
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
    delete_conversation_ai_conversations__cid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_available_models_ai_configs_models_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelCatalogRequest"];
            };
        };
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
    list_configs_ai_configs_get: {
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
                    "application/json": components["schemas"]["ConfigOut"][];
                };
            };
        };
    };
    create_config_ai_configs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfigBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedOut"];
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
    update_config_ai_configs__cid__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfigBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfigOut"];
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
    enable_config_ai_configs__cid__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
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
                    "application/json": components["schemas"]["EnableOut"];
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
    cancel_run_ai_runs__run_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
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
                    "application/json": components["schemas"]["CancelOut"];
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
    approve_action_ai_actions__action_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                } | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionResolveOut"];
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
    reject_action_ai_actions__action_id__reject_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                } | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionResolveOut"];
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
    list_grants_ai_grants_get: {
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
                    "application/json": components["schemas"]["ToolGrantOut"][];
                };
            };
        };
    };
    delete_grant_ai_grants__grant_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                grant_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    resume_stream_ai_conversations__cid__resume_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
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
                    "text/event-stream": string;
                };
            };
            /** @description 拒绝续跑：pending 非空=本轮仍有未决审批卡（按清单逐张处理）；consumed=true=该批次已被消费，无可恢复审批（幂等拒绝，re #023④） */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResumeBlockedOut"];
                    "text/event-stream": components["schemas"]["ResumeBlockedOut"];
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
    approve_plan_ai_conversations__cid__plans__plan_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                } | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": string;
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
    reject_plan_ai_conversations__cid__plans__plan_id__reject_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
                plan_id: number;
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
                    "application/json": components["schemas"]["PlanRejectOut"];
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
    list_skills_ai_skills_get: {
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
                    "application/json": components["schemas"]["SkillOut"][];
                };
            };
        };
    };
    create_skill_ai_skills_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SkillBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedOut"];
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
    enable_skill_ai_skills__sid__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
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
                    "application/json": components["schemas"]["EnableOut"];
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
    disable_active_skill_ai_skills_disable_active_post: {
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
                    "application/json": components["schemas"]["EnableOut"];
                };
            };
        };
    };
    delete_skill_ai_skills__sid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_mcp_servers_ai_mcp_servers_get: {
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
                    "application/json": components["schemas"]["MCPServerOut"][];
                };
            };
        };
    };
    create_mcp_server_ai_mcp_servers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MCPServerBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedOut"];
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
    update_mcp_server_ai_mcp_servers__sid__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MCPServerUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MCPServerOut"];
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
    delete_mcp_server_ai_mcp_servers__sid__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    enable_mcp_server_ai_mcp_servers__sid__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["MCPEnableBody"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EnableOut"];
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
    test_mcp_server_ai_mcp_servers__sid__test_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
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
                    "application/json": components["schemas"]["MCPTestOut"];
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
    list_mcp_server_tools_ai_mcp_servers__sid__tools_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sid: number;
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
                    "application/json": components["schemas"]["MCPToolOut"][];
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
    create_report_ai_reports__report_type__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_type: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ReportBody"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportOut"];
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
    list_reports_ai_reports_get: {
        parameters: {
            query?: {
                report_type?: string | null;
                limit?: number;
            };
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
                    "application/json": components["schemas"]["ReportOut"][];
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
    today_briefing_ai_briefing_today_get: {
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
                    "application/json": components["schemas"]["ReportOut"];
                };
            };
        };
    };
    report_detail_ai_reports__report_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_id: number;
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
                    "application/json": components["schemas"]["ReportOut"];
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
    delete_report_ai_reports__report_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_entries_api_ledger_get: {
        parameters: {
            query?: {
                start?: string | null;
                end?: string | null;
                currency?: ("CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY") | null;
                account?: string | null;
                direction?: ("income" | "expense") | null;
                query?: string;
                deleted?: boolean;
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["EntryPage"];
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
    create_entry_api_ledger_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EntryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntryRead"];
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
    summary_api_ledger_summary_get: {
        parameters: {
            query: {
                start: string;
                end: string;
                currency?: ("CNY" | "USD" | "EUR" | "GBP" | "HKD" | "JPY") | null;
                account?: string | null;
            };
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
                    "application/json": components["schemas"]["LedgerSummary"];
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
    get_entry_api_ledger__entry_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
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
                    "application/json": components["schemas"]["EntryRead"];
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
    replace_entry_api_ledger__entry_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EntryReplace"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntryRead"];
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
    delete_entry_api_ledger__entry_id__delete: {
        parameters: {
            query: {
                version: number;
            };
            header?: never;
            path: {
                entry_id: number;
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
                    "application/json": components["schemas"]["EntryRead"];
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
    restore_entry_api_ledger__entry_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntryRead"];
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
    list_bills_api_bills_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["BillPage"];
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
    create_api_bills_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillRead"];
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
    read_api_bills__bill_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_id: number;
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
                    "application/json": components["schemas"]["BillRead"];
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
    replace_api_bills__bill_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bill_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillRead"];
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
    history_api_bills__bill_id__history_get: {
        parameters: {
            query?: {
                before?: number | null;
            };
            header?: never;
            path: {
                bill_id: number;
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
                    "application/json": components["schemas"]["BillHistory"];
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
    pay_api_bills_occurrences__occurrence_id__pay_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                occurrence_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillPayment"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillOccurrenceRead"];
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
    read_occurrence_api_bills_occurrences__occurrence_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                occurrence_id: number;
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
                    "application/json": components["schemas"]["BillOccurrenceRead"];
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
    skip_api_bills_occurrences__occurrence_id__skip_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                occurrence_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BillSkip"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillOccurrenceRead"];
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
    list_items_api_inbox_get: {
        parameters: {
            query?: {
                status?: ("pending" | "applied" | "rejected") | null;
                source_file_id?: number | null;
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["InboxPage"];
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
    capture_api_inbox_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaptureBatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxRead"][];
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
    get_item_api_inbox__item_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
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
                    "application/json": components["schemas"]["InboxRead"];
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
    revise_api_inbox__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Revision"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxRead"];
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
    apply_item_api_inbox__item_id__apply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxRead"];
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
    reject_api_inbox__item_id__reject_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxRead"];
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
    read_watch_api_research_projects__project_id__watch_get: {
        parameters: {
            query?: {
                before?: number | null;
            };
            header?: never;
            path: {
                project_id: number;
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
                    "application/json": components["schemas"]["WatchRead"];
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
    configure_watch_api_research_projects__project_id__watch_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WatchUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WatchRead"];
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
    run_watch_api_research_projects__project_id__watch_run_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
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
                    "application/json": components["schemas"]["WatchRunRead"];
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
    list_projects_api_research_projects_get: {
        parameters: {
            query?: {
                archived?: boolean;
            };
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
                    "application/json": components["schemas"]["ProjectRead"][];
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
    create_project_api_research_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectRead"];
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
    detail_api_research_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
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
                    "application/json": components["schemas"]["ProjectDetail"];
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
    update_project_api_research_projects__project_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectRead"];
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
    archive_api_research_projects__project_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArchiveInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectRead"];
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
    gather_api_research_projects__project_id__sources_gather_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GatherInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatherResult"];
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
    add_source_api_research_projects__project_id__sources_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddSourceInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceRead"];
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
    attach_material_api_research_projects__project_id__materials_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceRead"];
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
    fetch_source_api_research_projects__project_id__sources__source_id__fetch_post: {
        parameters: {
            query?: {
                refresh?: boolean;
            };
            header?: never;
            path: {
                project_id: number;
                source_id: number;
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
                    "application/json": components["schemas"]["SourceRead"];
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
    plan_history_api_research_projects__project_id__plans_get: {
        parameters: {
            query?: {
                before?: number | null;
            };
            header?: never;
            path: {
                project_id: number;
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
                    "application/json": components["schemas"]["PlanHistory"];
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
    preview_plan_api_research_projects__project_id__plans_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanDraft"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanRead"];
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
    preview_replan_api_research_projects__project_id__replan_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanRead"];
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
    preview_extension_api_research_projects__project_id__extensions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExtensionDraft"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanRead"];
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
    preview_revision_api_research_projects__project_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RevisionDraft"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanRead"];
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
    list_feedback_api_research_projects__project_id__feedback_get: {
        parameters: {
            query?: {
                before?: number | null;
            };
            header?: never;
            path: {
                project_id: number;
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
                    "application/json": components["schemas"]["FeedbackPage"];
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
    record_feedback_api_research_projects__project_id__feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FeedbackCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeedbackRead"];
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
    withdraw_feedback_api_research_projects__project_id__feedback__feedback_id__withdraw_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
                feedback_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeedbackRead"];
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
    get_plan_api_research_plans__plan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
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
                    "application/json": components["schemas"]["PlanRead"];
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
    apply_plan_api_research_plans__plan_id__apply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
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
                    "application/json": components["schemas"]["PlanRead"];
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
    list_followups_api_followups_get: {
        parameters: {
            query?: {
                project_id?: number | null;
            };
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
                    "application/json": components["schemas"]["FollowupRead"][];
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
    status_api_followups_status_get: {
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
                    "application/json": components["schemas"]["FollowupStatus"];
                };
            };
        };
    };
    preferences_api_followups_preferences_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowupPreferences"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FollowupStatus"];
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
    check_api_followups_check_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowupCheck"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FollowupRead"] | null;
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
    get_followup_api_followups__followup_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                followup_id: number;
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
                    "application/json": components["schemas"]["FollowupRead"];
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
    apply_api_followups__followup_id__apply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                followup_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FollowupRead"];
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
    respond_api_followups__followup_id__respond_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                followup_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowupResponse"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FollowupRead"];
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
    search_api_materials_search_get: {
        parameters: {
            query: {
                query: string;
                file_id?: number | null;
                project_id?: number | null;
                file_offset?: number;
                limit?: number;
            };
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
                    "application/json": components["schemas"]["MaterialSearch"];
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
    read_api_materials__file_id__get: {
        parameters: {
            query?: {
                part?: number;
                count?: number;
                revision?: string | null;
            };
            header?: never;
            path: {
                file_id: number;
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
                    "application/json": components["schemas"]["MaterialRead"];
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
    get_web_services_ai_web_services_get: {
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
                    "application/json": components["schemas"]["WebServicesOut"];
                };
            };
        };
    };
    put_web_services_ai_web_services_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WebServicesConfig"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WebServicesOut"];
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
    put_tavily_key_ai_web_services_credentials_tavily_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CredentialBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CredentialOut"];
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
    delete_tavily_key_ai_web_services_credentials_tavily_delete: {
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
                    "application/json": components["schemas"]["CredentialOut"];
                };
            };
        };
    };
    search_web_ai_web_services_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SearchBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": (components["schemas"]["SearchHit"] | components["schemas"]["SearchError"])[];
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
    fetch_web_ai_web_services_fetch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FetchBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FetchOut"];
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
    get_vision_ai_vision_get: {
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
                    "application/json": components["schemas"]["VisionConfig"];
                };
            };
        };
    };
    save_vision_ai_vision_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VisionConfig"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VisionConfig"];
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
    clear_vision_ai_vision_delete: {
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
                    "application/json": components["schemas"]["VisionConfig"];
                };
            };
        };
    };
    workspace_ai_workspaces__surface__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                surface: "main" | "widget";
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
                    "application/json": components["schemas"]["WorkspaceOut"];
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
    save_workspace_ai_workspaces__surface__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                surface: "main" | "widget";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceOut"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceOut"];
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
    cancel_pending_ai_conversations__cid__pending_cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelPendingBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelPendingOut"];
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
    conversation_state_ai_conversations__cid__state_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                cid: number;
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
                    "application/json": components["schemas"]["ConversationStateOut"];
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
    health_health_get: {
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    shutdown_shutdown_post: {
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
}
