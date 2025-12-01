import React, { useState, useEffect } from 'react'
import './SchedulePanel.css'

function SchedulePanel({ app, apiBaseUrl, getAuthToken, cognitoEnabled }) {
  const [schedule, setSchedule] = useState({
    enabled: false,
    on: '09:00',
    off: '18:00',
    weekdays: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  useEffect(() => {
    if (app) {
      fetchSchedule()
    }
  }, [app])

  const fetchSchedule = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (cognitoEnabled) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
        }
      }

      const response = await fetch(`${apiBaseUrl}/apps/${app.app_name}/schedule`, {
        method: 'GET',
        headers
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      // Use global schedule values (read-only)
      setSchedule({
        enabled: data.enabled || false,
        on: data.on || '09:00',
        off: data.off || '22:00',
        weekdays: data.weekdays || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
        weekend_shutdown: data.weekend_shutdown !== undefined ? data.weekend_shutdown : true,
        read_only: data.read_only || false,
        message: data.message || null
      })
    } catch (err) {
      console.error('Error fetching schedule:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Schedule editing is disabled - only enable/disable toggle works
  // This function is no longer used but kept for backward compatibility
  const handleSave = async () => {
    setError('Schedule editing is disabled. Times are centrally configured and cannot be edited.')
    setMessage(null)
  }

  const handleToggleEnabled = async () => {
    setSaving(true)
    setError(null)

    try {
      const headers = { 'Content-Type': 'application/json' }
      if (cognitoEnabled) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
        }
      }

      const response = await fetch(`${apiBaseUrl}/apps/${app.app_name}/schedule/enable`, {
        method: 'POST',
        headers
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      setSchedule(prev => ({ ...prev, enabled: data.enabled }))
    } catch (err) {
      console.error('Error toggling schedule:', err)
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleWeekday = (day) => {
    setSchedule(prev => {
      const weekdays = prev.weekdays || []
      if (weekdays.includes(day)) {
        return { ...prev, weekdays: weekdays.filter(d => d !== day) }
      } else {
        return { ...prev, weekdays: [...weekdays, day] }
      }
    })
  }

  if (loading) {
    return <div className="schedule-panel loading">Loading schedule...</div>
  }

  return (
    <div className="schedule-panel">
      <div className="schedule-header">
        <h3>Auto-Schedule</h3>
        <div className="schedule-toggle">
          <label className="switch">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={handleToggleEnabled}
              disabled={saving}
            />
            <span className="slider"></span>
          </label>
          <span className="toggle-label">
            {schedule.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      </div>

      {!schedule.enabled && (
        <div className="schedule-warning">
          ⚠️ Auto-scheduling is disabled for this app
        </div>
      )}

      {error && (
        <div className="schedule-error">
          Error: {error}
        </div>
      )}

      {message && (
        <div className="schedule-success">
          {message}
        </div>
      )}

      <div className="schedule-form">
        {schedule.read_only && schedule.message && (
          <div className="schedule-info-message">
            ℹ️ {schedule.message}
          </div>
        )}

        <div className="form-group">
          <label>Start Time (IST):</label>
          <input
            type="time"
            value={schedule.on}
            disabled={true}
            readOnly
            className="read-only-input"
          />
          <small className="read-only-label">Read-only (centrally configured)</small>
        </div>

        <div className="form-group">
          <label>Stop Time (IST):</label>
          <input
            type="time"
            value={schedule.off}
            disabled={true}
            readOnly
            className="read-only-input"
          />
          <small className="read-only-label">Read-only (centrally configured)</small>
        </div>

        <div className="form-group">
          <label>Weekdays:</label>
          <div className="weekdays-selector">
            {weekdays.map(day => (
              <label key={day} className="weekday-checkbox disabled">
                <input
                  type="checkbox"
                  checked={schedule.weekdays?.includes(day)}
                  disabled={true}
                  readOnly
                />
                <span className={schedule.weekdays?.includes(day) ? 'checked' : ''}>{day}</span>
              </label>
            ))}
          </div>
          <small className="read-only-label">Read-only (centrally configured)</small>
        </div>

        {schedule.weekend_shutdown && (
          <div className="form-group">
            <label>Weekend:</label>
            <div className="weekend-info">
              <span className="weekend-shutdown-badge">🔴 Shutdown Enforced</span>
              <small>Apps are automatically stopped on Saturday and Sunday</small>
            </div>
          </div>
        )}

        <div className="schedule-note">
          <small>All times are in IST (Asia/Kolkata) timezone. Schedule times and weekdays are centrally configured and cannot be edited.</small>
        </div>
      </div>
    </div>
  )
}

export default SchedulePanel


