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
      if (data.on && data.off && data.weekdays) {
        setSchedule({
          enabled: data.enabled || false,
          on: data.on,
          off: data.off,
          weekdays: data.weekdays || []
        })
      }
    } catch (err) {
      console.error('Error fetching schedule:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setMessage(null)

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
        method: 'POST',
        headers,
        body: JSON.stringify(schedule)
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || `HTTP ${response.status}`)
      }

      setMessage('Schedule saved successfully!')
      setTimeout(() => setMessage(null), 3000)
    } catch (err) {
      console.error('Error saving schedule:', err)
      setError(err.message)
    } finally {
      setSaving(false)
    }
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
        <div className="form-group">
          <label>Start Time (IST):</label>
          <input
            type="time"
            value={schedule.on}
            onChange={(e) => setSchedule(prev => ({ ...prev, on: e.target.value }))}
            disabled={!schedule.enabled || saving}
          />
        </div>

        <div className="form-group">
          <label>Stop Time (IST):</label>
          <input
            type="time"
            value={schedule.off}
            onChange={(e) => setSchedule(prev => ({ ...prev, off: e.target.value }))}
            disabled={!schedule.enabled || saving}
          />
        </div>

        <div className="form-group">
          <label>Weekdays:</label>
          <div className="weekdays-selector">
            {weekdays.map(day => (
              <label key={day} className="weekday-checkbox">
                <input
                  type="checkbox"
                  checked={schedule.weekdays?.includes(day)}
                  onChange={() => toggleWeekday(day)}
                  disabled={!schedule.enabled || saving}
                />
                <span>{day}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="schedule-note">
          <small>All times are in IST (Asia/Kolkata) timezone</small>
        </div>

        <button
          className="save-button"
          onClick={handleSave}
          disabled={saving || !schedule.enabled}
        >
          {saving ? 'Saving...' : 'Save Schedule'}
        </button>
      </div>
    </div>
  )
}

export default SchedulePanel


