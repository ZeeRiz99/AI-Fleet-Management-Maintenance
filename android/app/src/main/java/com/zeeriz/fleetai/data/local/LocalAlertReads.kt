package com.zeeriz.fleetai.data.local

import android.content.Context

/** Alerts marked as read while browsing the read-only GitHub data (kept on this phone only). */
interface AlertReadStore {
    fun ids(): Set<String>
    fun add(ids: Collection<String>)
    fun clear()
}

class LocalAlertReads(context: Context) : AlertReadStore {
    private val prefs = context.applicationContext.getSharedPreferences("github_alert_reads", Context.MODE_PRIVATE)

    override fun ids(): Set<String> = prefs.getStringSet(KEY, emptySet()).orEmpty()

    override fun add(ids: Collection<String>) {
        if (ids.isEmpty()) return
        prefs.edit().putStringSet(KEY, ids() + ids).apply()
    }

    override fun clear() = prefs.edit().remove(KEY).apply()

    private companion object {
        const val KEY = "read_ids"
    }
}
