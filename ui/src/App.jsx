import React, { useState, useEffect, useMemo } from 'react'
import './App.css'
import Login from './components/Login'
import CostBreakdownModal from './components/CostBreakdownModal'
import SchedulePanel from './components/SchedulePanel'
import DatabaseControlModal from './components/DatabaseControlModal'
import { getAuthToken, isAuthenticated, signOut } from './auth/cognito'

// Get API URL from environment or use default
// Priority: VITE_API_URL env var > default
// Note: config.json is loaded dynamically in useEffect below
const API_BASE_URL_DEFAULT = import.meta.env.VITE_API_URL || 'https://YOUR_API_GATEWAY_URL.execute-api.us-east-1.amazonaws.com'

// Check if Cognito is configured (optional - allows fallback to no-auth mode)
const COGNITO_ENABLED = !!(import.meta.env.VITE_COGNITO_USER_POOL_ID && import.meta.env.VITE_COGNITO_CLIENT_ID)

// Log Cognito status for debugging (remove in production if needed)
if (typeof window !== 'undefined') {
  console.log('Cognito Enabled:', COGNITO_ENABLED)
}

function App() {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState({})
  const [darkMode, setDarkMode] = useState(localStorage.getItem('darkMode') === 'true')
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortBy, setSortBy] = useState('app_name')
  const [sortOrder, setSortOrder] = useState('asc')
  const [expandedApps, setExpandedApps] = useState(new Set())
  const [lastUpdated, setLastUpdated] = useState(null)
  const [authenticated, setAuthenticated] = useState(!COGNITO_ENABLED) // If Cognito disabled, start authenticated
  const [checkingAuth, setCheckingAuth] = useState(COGNITO_ENABLED) // Check auth if Cognito enabled
  const [costModalApp, setCostModalApp] = useState(null)
  const [apiBaseUrl, setApiBaseUrl] = useState(API_BASE_URL_DEFAULT)
  const [dbControlModal, setDbControlModal] = useState(null) // { app, dbType, action }

  // Load API URL from config.json on mount
  useEffect(() => {
    const loadApiUrl = async () => {
      try {
        // Try to load from config.json first
        const configResponse = await fetch('/config.json')
        if (configResponse.ok) {
          const config = await configResponse.json()
          if (config.apiUrl) {
            setApiBaseUrl(config.apiUrl)
            console.log('API URL loaded from config.json:', config.apiUrl)
            return
          }
        }
      } catch (err) {
        console.warn('Could not load config.json, using default:', err)
      }
      
      // Fallback to environment variable or default
      if (import.meta.env.VITE_API_URL) {
        setApiBaseUrl(import.meta.env.VITE_API_URL)
        console.log('API URL from environment variable:', import.meta.env.VITE_API_URL)
      } else {
        // Use the default (which should be set during build)
        setApiBaseUrl(API_BASE_URL_DEFAULT)
        console.log('Using default API URL:', API_BASE_URL_DEFAULT)
      }
    }
    
    loadApiUrl()
  }, [])

  // Check authentication on mount
  useEffect(() => {
    if (COGNITO_ENABLED) {
      checkAuth()
    }
  }, [])

  const checkAuth = async () => {
    try {
      const isAuth = await isAuthenticated()
      setAuthenticated(isAuth)
    } catch (err) {
      console.error('Auth check failed:', err)
      setAuthenticated(false)
    } finally {
      setCheckingAuth(false)
    }
  }

  const handleLoginSuccess = () => {
    setAuthenticated(true)
    fetchApps(true)
  }

  const handleLogout = () => {
    signOut()
    setAuthenticated(false)
    setApps([])
  }

  // Initial load (only if authenticated)
  useEffect(() => {
    if (authenticated) {
      fetchApps(true)
      // Auto-refresh every 5 seconds for immediate updates
      const interval = setInterval(() => fetchApps(false), 5000)
      return () => clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated])

  useEffect(() => {
    document.documentElement.classList.toggle('dark-mode', darkMode)
    localStorage.setItem('darkMode', darkMode)
  }, [darkMode])

  const fetchApps = async (isInitialLoad = false) => {
    try {
      if (isInitialLoad) {
        setLoading(true)
      } else {
        setIsRefreshing(true)
      }
      
      console.log('Fetching apps from:', `${apiBaseUrl}/apps`)
      
      // Build headers with authentication token if Cognito is enabled
      const headers = {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
      }
      
      if (COGNITO_ENABLED) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
          // If token fetch fails, user needs to re-authenticate
          if (err.message === 'Session expired' || err.message === 'No user') {
            setAuthenticated(false)
            return
          }
        }
      }
      
      const response = await fetch(`${apiBaseUrl}/apps`, {
        method: 'GET',
        mode: 'cors',
        cache: 'no-cache',
        headers
      })
      
      console.log('Response status:', response.status, response.statusText)
      console.log('Response headers:', Object.fromEntries(response.headers.entries()))
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('API Error:', response.status, errorText)
        throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 100)}`)
      }
      
      const data = await response.json()
      console.log('Apps received:', data.apps?.length || 0)
      
      // Fetch cost data for each app in parallel
      const appsWithCosts = await Promise.all(
        (data.apps || []).map(async (app) => {
          const appName = app.name || app.app_name || app.hostname
          if (!appName) return app
          
          try {
            const costResponse = await fetch(`${apiBaseUrl}/apps/${encodeURIComponent(appName)}/cost`, {
              method: 'GET',
              headers: {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
              }
            })
            
            if (costResponse.ok) {
              const costData = await costResponse.json()
              return { ...app, cost_data: costData }
            }
          } catch (err) {
            console.warn(`Failed to fetch cost for ${appName}:`, err)
          }
          
          return app
        })
      )
      
      // Debug: Log pod data for first app
      if (appsWithCosts && appsWithCosts.length > 0) {
        const firstApp = appsWithCosts[0]
        console.log('Sample app pod data:', {
          app: firstApp.name || firstApp.app_name,
          pods: firstApp.pods,
          namespace: firstApp.namespace
        })
      }
      
      // Normalize API response format (new format -> old format for UI compatibility)
      const normalizedApps = appsWithCosts.map(app => {
        // New format: { http: { status, code, latency_ms }, postgres: { state, host, port }, ... }
        // Old format: { status, http_status_code, http_latency_ms, postgres_state, postgres_host, ... }
        if (app.http) {
          // Get app name from multiple possible fields
          const appName = app.name || app.app || app.hostname || app.hostnames?.[0] || 'Unknown App'
          const hostnames = app.hostnames || (app.hostname ? [app.hostname] : []) || (app.name ? [app.name] : []) || []
          
          // Determine nodegroup_state from nodegroups array
          let nodegroup_state = null
          if (app.nodegroups && app.nodegroups.length > 0) {
            const ng = app.nodegroups[0]
            const ng_status = ng.status
            if (ng_status === 'ACTIVE' && ng.current && ng.current > 0) {
              nodegroup_state = 'ready'
            } else if (ng_status === 'ACTIVE' || ng_status === 'UPDATING' || ng_status === 'CREATING') {
              nodegroup_state = 'scaling'
            } else if (ng_status === 'DELETING' || ng_status === 'DEGRADED') {
              nodegroup_state = 'stopped'
            } else {
              nodegroup_state = 'unknown'
            }
          }
          
          return {
            ...app,
            app_name: appName,  // Primary field for UI
            name: appName,  // Also set name field
            hostname: app.hostname || app.hostnames?.[0] || app.name || app.app || null,
            hostnames: hostnames.length > 0 ? hostnames : [appName],  // Always have at least one
            namespace: app.namespace || 'default',
            status: app.http.status,
            http_status_code: app.http.code,
            http_latency_ms: app.http.latency_ms,
            postgres_state: app.postgres?.state,
            postgres_host: app.postgres?.host,
            postgres_port: app.postgres?.port,
            neo4j_state: app.neo4j?.state,
            neo4j_host: app.neo4j?.host,
            neo4j_port: app.neo4j?.port,
            nodegroup_state: nodegroup_state,  // Derived from nodegroups array
            nodegroups: (app.nodegroups && Array.isArray(app.nodegroups)) ? app.nodegroups : (app.nodegroups ? [app.nodegroups] : []),  // Ensure nodegroups is always an array
            pods: app.pods || { running: 0, pending: 0, crashloop: 0, total: 0 },  // Preserve pods object
            final_app_status: app.http.status
          }
        }
        // Already in old format, ensure name fields are set
        const appName = app.app_name || app.name || app.hostname || app.hostnames?.[0] || 'Unknown App'
        return {
          ...app,
          app_name: appName,
          name: appName,
          hostname: app.hostname || app.hostnames?.[0] || appName,
          hostnames: app.hostnames || (app.hostname ? [app.hostname] : []) || [appName],
          nodegroups: app.nodegroups || [],  // Preserve nodegroups
          pods: app.pods || { running: 0, pending: 0, crashloop: 0, total: 0 }  // Preserve pods
        }
      })
      
      setApps(normalizedApps)
      setError(null)
      setLastUpdated(new Date())
    } catch (err) {
      console.error('Error fetching apps:', err)
      console.error('Error details:', {
        message: err.message,
        name: err.name,
        stack: err.stack
      })
      // Only show error on initial load, not on auto-refresh
      if (isInitialLoad) {
        setError(`Failed to load applications: ${err.message}. Check browser console (F12) for details.`)
      }
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }

  const toggleExpanded = (appName) => {
    const newExpanded = new Set(expandedApps)
    if (newExpanded.has(appName)) {
      newExpanded.delete(appName)
    } else {
      newExpanded.add(appName)
    }
    setExpandedApps(newExpanded)
  }

  const handleStart = async (appName) => {
    // Step 1: Get preview (dry-run)
    try {
      // Build headers with authentication token if Cognito is enabled
      const headers = { 'Content-Type': 'application/json' }
      if (COGNITO_ENABLED) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
          setAuthenticated(false)
          return
        }
      }
      
      // Get preview
      const previewResponse = await fetch(`${apiBaseUrl}/start?dry_run=true`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ app_name: appName })
      })
      
      if (!previewResponse.ok) {
        throw new Error(`HTTP ${previewResponse.status}`)
      }
      
      const preview = await previewResponse.json()
      
      // Check if it's a preview response
      if (preview.dry_run) {
        // Build preview message
        const summary = preview.summary || {}
        const actions = preview.actions || []
        const warnings = preview.warnings || []
        
        let previewMessage = `Start Application: ${appName}\n\n`
        previewMessage += `Planned Actions:\n`
        previewMessage += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`
        
        if (summary.ec2_instances_to_start > 0) {
          const ec2Actions = actions.filter(a => a.type === 'start_ec2')
          previewMessage += `EC2 Instances to Start: ${summary.ec2_instances_to_start}\n`
          ec2Actions.forEach(action => {
            previewMessage += `  • ${action.resource.toUpperCase()}: ${action.instance_id} (${action.current_state} → ${action.target_state})\n`
          })
          previewMessage += `\n`
        }
        
        if (summary.nodegroups_to_scale > 0) {
          const ngActions = actions.filter(a => a.type === 'scale_nodegroup')
          previewMessage += `NodeGroups to Scale: ${summary.nodegroups_to_scale}\n`
          ngActions.forEach(action => {
            previewMessage += `  • ${action.nodegroup}: desired ${action.current_desired} → ${action.target_desired}, min ${action.current_min} → ${action.target_min}, max ${action.current_max} → ${action.target_max}\n`
          })
          previewMessage += `\n`
        }
        
        if (summary.deployments_to_scale > 0) {
          const deployActions = actions.filter(a => a.type === 'scale_deployment')
          previewMessage += `Deployments to Scale: ${summary.deployments_to_scale}\n`
          deployActions.forEach(action => {
            previewMessage += `  • ${action.name}: ${action.current_replicas} → ${action.target_replicas} replicas\n`
          })
          previewMessage += `\n`
        }
        
        if (summary.statefulsets_to_scale > 0) {
          const stsActions = actions.filter(a => a.type === 'scale_statefulset')
          previewMessage += `StatefulSets to Scale: ${summary.statefulsets_to_scale}\n`
          stsActions.forEach(action => {
            previewMessage += `  • ${action.name}: ${action.current_replicas} → ${action.target_replicas} replicas\n`
          })
          previewMessage += `\n`
        }
        
        if (warnings.length > 0) {
          previewMessage += `Warnings:\n`
          warnings.forEach(warning => {
            previewMessage += `  ⚠️  ${warning}\n`
          })
          previewMessage += `\n`
        }
        
        if (actions.length === 0) {
          previewMessage += `No actions needed - application is already in the desired state.\n\n`
        }
        
        previewMessage += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n`
        previewMessage += `Do you want to proceed with starting this application?`
        
        // Show confirmation dialog
        const confirmed = window.confirm(previewMessage)
        if (!confirmed) {
          return
        }
      }
    } catch (err) {
      console.error('Error getting preview:', err)
      // Continue with execution even if preview fails
    }
    
    // Step 2: Execute actual start
    setActionLoading({ ...actionLoading, [appName]: 'starting' })
    try {
      const requestBody = { app_name: appName }
      
      // Build headers with authentication token if Cognito is enabled
      const headers = { 'Content-Type': 'application/json' }
      if (COGNITO_ENABLED) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
          setAuthenticated(false)
          setActionLoading({ ...actionLoading, [appName]: null })
          return
        }
      }
      
      const response = await fetch(`${apiBaseUrl}/start`, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody)
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      
      if (data.success) {
        const details = []
        
        // Show database status
        if (data.step1_postgres?.length > 0) {
          details.push(`✅ PostgreSQL: Started and healthy`)
        } else if (data.warnings?.some(w => w.includes('PostgreSQL') && w.includes('SHARED'))) {
          details.push(`ℹ️  PostgreSQL: Using shared database (skipped start)`)
        }
        
        if (data.step2_neo4j?.length > 0) {
          details.push(`✅ Neo4j: Started and healthy`)
        } else if (data.warnings?.some(w => w.includes('Neo4j') && w.includes('SHARED'))) {
          details.push(`ℹ️  Neo4j: Using shared database (skipped start)`)
        }
        
        if (data.step3_nodegroups?.length > 0) {
          details.push(`✅ NodeGroups: Scaled to defaults`)
        }
        
        if (data.step4_workloads) {
          const deployments = data.step4_workloads.deployments?.length || 0
          const statefulsets = data.step4_workloads.statefulsets?.length || 0
          details.push(`✅ Deployments: ${deployments} scaled to 1`)
          details.push(`✅ StatefulSets: ${statefulsets} scaled to 1`)
        }
        
        if (data.step5_http?.accessible) {
          details.push(`✅ HTTP: Accessible (${data.step5_http.http_status}, ${data.step5_http.response_time_ms}ms)`)
        }
        
        const message = details.length > 0 
          ? `Application ${appName} started successfully!\n\n${details.join('\n')}`
          : `Application ${appName} started successfully!`
        
        alert(message)
        // Refresh immediately after action
        setTimeout(() => fetchApps(true), 1000)
      } else {
        const errorMsg = data.error || data.errors?.join('\n') || 'Unknown error'
        const warnings = data.warnings?.length > 0 ? `\n\nWarnings:\n${data.warnings.join('\n')}` : ''
        alert(`Failed to start: ${errorMsg}${warnings}`)
      }
    } catch (err) {
      console.error('Error starting app:', err)
      alert(`Error starting application: ${err.message}`)
    } finally {
      setActionLoading({ ...actionLoading, [appName]: null })
    }
  }

  const handleStop = async (appName) => {
    const app = apps.find(a => a.app_name === appName)
    const sharedResources = app?.shared_resources || {}
    const hasShared = (sharedResources.postgres?.length > 0) || (sharedResources.neo4j?.length > 0)
    
    if (hasShared) {
      const confirmMsg = `Warning: This application has shared database resources that cannot be stopped.\n\n` +
        `PostgreSQL: ${sharedResources.postgres?.map(p => p.host || p.instance_id || 'Unknown').join(', ') || 'None'}\n` +
        `Neo4j: ${sharedResources.neo4j?.map(n => n.host || n.instance_id || 'Unknown').join(', ') || 'None'}\n\n` +
        `These databases will remain running. Continue with shutdown?`
      
      if (!window.confirm(confirmMsg)) {
        return
      }
    }
    
    setActionLoading({ ...actionLoading, [appName]: 'stopping' })
    try {
      // Build headers with authentication token if Cognito is enabled
      const headers = { 'Content-Type': 'application/json' }
      if (COGNITO_ENABLED) {
        try {
          const token = await getAuthToken()
          headers['Authorization'] = `Bearer ${token}`
        } catch (err) {
          console.error('Failed to get auth token:', err)
          setAuthenticated(false)
          setActionLoading({ ...actionLoading, [appName]: null })
          return
        }
      }
      
      const response = await fetch(`${apiBaseUrl}/stop`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ app_name: appName })
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      
      if (data.success) {
        const details = []
        
        // Show scaling status
        if (data.step1_deployments?.length > 0 || data.step2_statefulsets?.length > 0) {
          const deployments = data.step1_deployments?.length || 0
          const statefulsets = data.step2_statefulsets?.length || 0
          details.push(`✅ Deployments: ${deployments} scaled to 0`)
          details.push(`✅ StatefulSets: ${statefulsets} scaled to 0`)
        }
        
        if (data.step3_nodegroups?.length > 0) {
          details.push(`✅ NodeGroups: Scaled down`)
        }
        
        // Show database status
        if (data.postgres?.length > 0) {
          const pg = data.postgres[0]
          if (pg.shared) {
            details.push(`✅ PostgreSQL: Stopped unused shared instance`)
          } else {
            details.push(`✅ PostgreSQL: Stopped dedicated instance`)
          }
        } else if (data.warnings?.some(w => w.includes('PostgreSQL') && w.includes('shared'))) {
          details.push(`ℹ️  PostgreSQL: Shared database (skipped stop)`)
        }
        
        if (data.neo4j?.length > 0) {
          const neo = data.neo4j[0]
          if (neo.shared) {
            details.push(`✅ Neo4j: Stopped unused shared instance`)
          } else {
            details.push(`✅ Neo4j: Stopped dedicated instance`)
          }
        } else if (data.warnings?.some(w => w.includes('Neo4j') && w.includes('shared'))) {
          details.push(`ℹ️  Neo4j: Shared database (skipped stop)`)
        }
        
        const warnings = data.warnings || []
        const message = details.length > 0 
          ? `Application ${appName} stopped successfully!\n\n${details.join('\n')}${warnings.length > 0 ? '\n\nWarnings:\n' + warnings.join('\n') : ''}`
          : `Application ${appName} stopped successfully!${warnings.length > 0 ? '\n\nWarnings:\n' + warnings.join('\n') : ''}`
        
        alert(message)
        // Refresh immediately after action
        setTimeout(() => fetchApps(true), 1000)
      } else {
        const errorMsg = data.error || data.errors?.join('\n') || 'Unknown error'
        const warnings = data.warnings?.length > 0 ? `\n\nWarnings:\n${data.warnings.join('\n')}` : ''
        alert(`Failed to stop: ${errorMsg}${warnings}`)
      }
    } catch (err) {
      console.error('Error stopping app:', err)
      alert(`Error stopping application: ${err.message}`)
    } finally {
      setActionLoading({ ...actionLoading, [appName]: null })
    }
  }

  // Helper to get consistent app name/identifier
  const getAppIdentifier = (app) => {
    return app.name || app.app_name || app.hostname || app.hostnames?.[0] || app.app || 'unknown'
  }

  // Component status helper functions
  const getComponentStatus = (app, componentType) => {
    const state = app[`${componentType}_state`]
    if (!state) {
      // For nodegroups, if we have nodegroups data but no state, infer from the array
      if (componentType === 'nodegroup' && app.nodegroups && app.nodegroups.length > 0) {
        const ng = app.nodegroups[0]
        if (ng.status === 'ACTIVE' && ng.current && ng.current > 0) {
          return 'green'
        } else if (ng.status === 'ACTIVE' || ng.status === 'UPDATING' || ng.status === 'CREATING') {
          return 'yellow'
        } else if (ng.status === 'DELETING' || ng.status === 'DEGRADED') {
          return 'red'
        }
      }
      return 'unknown'
    }
    if (state === 'running' || state === 'ready') return 'green'
    if (state === 'stopped') return 'red'
    if (state === 'starting' || state === 'scaling' || state === 'initializing') return 'yellow'
    return 'unknown'
  }

  const getComponentTooltip = (app, componentType) => {
    const state = app[`${componentType}_state`]
    if (!state) {
      // If no state but component exists, infer from data
      if (componentType === 'postgres' && app.postgres_host) return 'Not checked'
      if (componentType === 'neo4j' && app.neo4j_host) return 'Not checked'
      if (componentType === 'nodegroup') {
        // For nodegroups, try to infer from the array data
        if (app.nodegroups && app.nodegroups.length > 0) {
          const ng = app.nodegroups[0]
          if (ng.status) {
            if (ng.status === 'ACTIVE' && ng.current && ng.current > 0) {
              return `Active (${ng.current} nodes)`
            } else if (ng.status === 'ACTIVE') {
              return `Active (scaling)`
            } else {
              return ng.status
            }
          }
          return 'Not checked'
        }
        return 'N/A'
      }
      return 'N/A'
    }
    return state.charAt(0).toUpperCase() + state.slice(1).replace('_', ' ')
  }

  // Determine final app status - use exact status from API (HTTP-only)
  // HTTP status is authoritative: 200 = UP, everything else = DOWN
  // No component-based logic - components are informational only
  const getFinalAppStatus = (app) => {
    // Return exact status from API (from live HTTP check)
    // Status is 'UP' if HTTP 200, 'DOWN' otherwise
    return app.status || app.final_app_status || 'UNKNOWN'
  }

  const filteredAndSortedApps = useMemo(() => {
    let filtered = apps

    // Search filter
    if (searchTerm) {
      filtered = filtered.filter(app => {
        const appId = getAppIdentifier(app)
        return appId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        app.namespace?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (app.hostnames || []).some(h => h.toLowerCase().includes(searchTerm.toLowerCase()))
      })
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(app => {
        const finalStatus = getFinalAppStatus(app)
        return finalStatus === statusFilter
      })
    }

    // Sort
    filtered.sort((a, b) => {
      let aVal, bVal
      
      switch (sortBy) {
        case 'app_name':
          aVal = a.app_name || ''
          bVal = b.app_name || ''
          break
        case 'status':
          aVal = a.status || ''
          bVal = b.status || ''
          break
        case 'latency':
          aVal = a.http_latency_ms || 999999
          bVal = b.http_latency_ms || 999999
          break
        case 'namespace':
          aVal = a.namespace || ''
          bVal = b.namespace || ''
          break
        default:
          aVal = a.app_name || ''
          bVal = b.app_name || ''
      }

      if (sortOrder === 'asc') {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0
      } else {
        return aVal < bVal ? 1 : aVal > bVal ? -1 : 0
      }
    })

    return filtered
  }, [apps, searchTerm, statusFilter, sortBy, sortOrder])

  const getStatusIcon = (status) => {
    switch (status) {
      case 'UP':
        return '🟢'
      case 'DOWN':
        return '🔴'
      case 'DEGRADED':
        return '🟡'
      case 'WAITING':
        return '🟡'
      default:
        return '⚪'
    }
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'UP':
        return '#10b981'
      case 'DOWN':
        return '#ef4444'
      case 'DEGRADED':
        return '#f59e0b'
      case 'WAITING':
        return '#f59e0b'
      default:
        return '#6b7280'
    }
  }

  const getComponentStatusColor = (status) => {
    switch (status) {
      case 'green':
        return '#10b981'
      case 'red':
        return '#ef4444'
      case 'yellow':
        return '#f59e0b'
      default:
        return '#6b7280'
    }
  }

  const formatDate = (timestamp) => {
    if (!timestamp) return 'N/A'
    const date = new Date(timestamp * 1000)
    return date.toLocaleString()
  }

  // Show login screen if not authenticated
  if (checkingAuth) {
    return (
      <div className="app-container">
        <div className="loading">Checking authentication...</div>
      </div>
    )
  }

  if (!authenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  if (loading && apps.length === 0) {
    return (
      <div className="app-container">
        <div className="loading">Loading applications...</div>
      </div>
    )
  }

  return (
    <div className="app-container">
      <header className="header">
        <div>
          <h1>EKS Application Controller</h1>
          {COGNITO_ENABLED && (
            <button 
              onClick={handleLogout}
              className="logout-button"
              style={{ 
                marginLeft: '20px', 
                padding: '8px 16px', 
                background: '#dc3545', 
                color: 'white', 
                border: 'none', 
                borderRadius: '4px', 
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Logout
            </button>
          )}
          {lastUpdated && (
            <div className="last-updated">
              Last updated: {lastUpdated.toLocaleTimeString()}
              {isRefreshing && <span className="refreshing-indicator"> ⟳ Refreshing...</span>}
            </div>
          )}
        </div>
        <div className="header-actions">
          <button onClick={() => setDarkMode(!darkMode)} className="theme-toggle">
            {darkMode ? '☀️' : '🌙'}
          </button>
          <button onClick={() => fetchApps(true)} className="refresh-btn" disabled={loading || isRefreshing}>
            {loading || isRefreshing ? '⟳ Refreshing...' : '🔄 Refresh'}
          </button>
        </div>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      <div className="controls">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search by app name, namespace, or hostname..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-input"
          />
        </div>
        
        <div className="filters">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="filter-select">
            <option value="all">All Status</option>
            <option value="UP">UP</option>
            <option value="DOWN">DOWN</option>
            <option value="DEGRADED">DEGRADED</option>
          </select>
          
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="filter-select">
            <option value="app_name">Sort by Name</option>
            <option value="status">Sort by Status</option>
            <option value="latency">Sort by Latency</option>
            <option value="namespace">Sort by Namespace</option>
          </select>
          
          <button onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')} className="sort-btn">
            {sortOrder === 'asc' ? '↑' : '↓'}
          </button>
        </div>
      </div>

      <div className="apps-grid">
        {filteredAndSortedApps.map((app, index) => {
          const finalStatus = getFinalAppStatus(app)
          const postgresStatus = getComponentStatus(app, 'postgres')
          const neo4jStatus = getComponentStatus(app, 'neo4j')
          const nodegroupStatus = getComponentStatus(app, 'nodegroup')
          const appId = getAppIdentifier(app)
          
          return (
          <div key={appId || `app-${index}`} className="app-card">
            <div className="app-header">
              <div className="app-title">
                <div>
                  <h2 className="app-name-large">{appId}</h2>
                  {app.namespace && <span className="namespace-badge">{app.namespace}</span>}
                </div>
              </div>
              <div 
                className="status-badge-pill"
                style={{ backgroundColor: getStatusColor(finalStatus) }}
              >
                {finalStatus}
                {app.http_latency_ms && finalStatus === 'UP' && <span className="latency"> ({app.http_latency_ms}ms)</span>}
              </div>
            </div>

            {/* Component Status Indicators */}
            <div className="component-status-row">
              {(app.postgres_instances?.length > 0 || app.postgres_state) && (
                <div 
                  className="component-status-indicator"
                  title={`Postgres: ${getComponentTooltip(app, 'postgres')}`}
                >
                  <span className="component-label">Postgres:</span>
                  <span 
                    className="status-circle"
                    style={{ backgroundColor: getComponentStatusColor(postgresStatus) }}
                  ></span>
                </div>
              )}
              {(app.neo4j_instances?.length > 0 || app.neo4j_state) && (
                <div 
                  className="component-status-indicator"
                  title={`Neo4j: ${getComponentTooltip(app, 'neo4j')}`}
                >
                  <span className="component-label">Neo4j:</span>
                  <span 
                    className="status-circle"
                    style={{ backgroundColor: getComponentStatusColor(neo4jStatus) }}
                  ></span>
                </div>
              )}
              {/* Show Nodes indicator - use same logic as details section */}
              {/* If NodeGroups section shows data, indicator should show too */}
              {(app.nodegroups && (Array.isArray(app.nodegroups) ? app.nodegroups.length > 0 : app.nodegroups)) || app.nodegroup_state ? (
                <div 
                  className="component-status-indicator"
                  title={`Nodes: ${getComponentTooltip(app, 'nodegroup')}`}
                >
                  <span className="component-label">Nodes:</span>
                  <span 
                    className="status-circle"
                    style={{ backgroundColor: getComponentStatusColor(nodegroupStatus) }}
                  ></span>
                </div>
              ) : null}
            </div>

            <div className="app-details">
              <div className="detail-row">
                <span className="detail-label">Hostnames:</span>
                <span className="detail-value">
                  {app.hostnames && app.hostnames.length > 0 
                    ? (app.hostnames.length === 1 
                        ? app.hostnames[0] 
                        : app.hostnames.map((h, idx) => <span key={idx}>{h}{idx < app.hostnames.length - 1 ? ', ' : ''}</span>))
                    : (app.hostname || app.name || app.app_name || app.app || '(unknown)')}
                </span>
              </div>

              <button 
                className="expand-btn"
                onClick={() => toggleExpanded(appId)}
              >
                {expandedApps.has(appId) ? '▼' : '▶'} Details
              </button>

              {expandedApps.has(appId) && (
                <div className="expanded-details">
                  {/* NodeGroups */}
                  <div className="detail-section">
                    <h3>NodeGroups ({app.nodegroups && Array.isArray(app.nodegroups) ? app.nodegroups.length : (app.nodegroups ? 1 : 0)})</h3>
                    {app.nodegroups && (Array.isArray(app.nodegroups) ? app.nodegroups.length > 0 : true) ? (
                      app.nodegroups.map((ng, idx) => (
                        <div key={idx} className="detail-item">
                          <strong>{ng.name}</strong>
                          {ng.labels && Object.keys(ng.labels).length > 0 && (
                            <div className="labels">
                              {Object.entries(ng.labels).map(([k, v]) => (
                                <span key={k} className="label-badge">{k}={v}</span>
                              ))}
                            </div>
                          )}
                          <div className="scaling-info">
                            Desired: {ng.desired != null ? ng.desired : 'Unknown'} | 
                            Min: {ng.min != null ? ng.min : 'Unknown'} | 
                            Max: {ng.max != null ? ng.max : 'Unknown'}
                            {ng.current != null && <span> | Current: {ng.current}</span>}
                            {ng.status && <span className="nodegroup-status"> ({ng.status})</span>}
                          </div>
                          {ng.is_shared && (
                            <div className="shared-resource-warning">
                              🔗 <strong>Shared Resource</strong>
                              {ng.shared_with && ng.shared_with.length > 0 && (
                                <div className="shared-with">
                                  Shared with: {ng.shared_with.filter(a => a !== app.name && a !== app.app_name && a !== app.app).join(', ') || 'another application'}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="no-data">No NodeGroups</div>
                    )}
                  </div>

                  {/* Pods */}
                  <div className="detail-section">
                    <h3>Pods</h3>
                    {app.pods ? (
                      <div className="pods-info">
                        {/* Running Pods Dropdown */}
                        <div className="pod-status-group">
                          <details className="pod-dropdown">
                            <summary className={`pod-status running ${(app.pods.running || 0) > 0 ? 'has-pods' : ''}`}>
                              Running: {app.pods.running || 0} {(app.pods.running || 0) > 0 ? '▼' : ''}
                            </summary>
                            {app.pods.running_list && app.pods.running_list.length > 0 ? (
                              <ul className="pod-list">
                                {app.pods.running_list.map((pod, idx) => (
                                  <li key={idx} className="pod-item">
                                    <strong>{pod.name}</strong>
                                    {pod.owner && <span className="pod-owner"> ({pod.owner})</span>}
                                    {pod.created && <span className="pod-created"> • Created: {new Date(pod.created).toLocaleString()}</span>}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <div className="no-pods">No running pods</div>
                            )}
                          </details>
                        </div>

                        {/* Pending Pods Dropdown */}
                        <div className="pod-status-group">
                          <details className="pod-dropdown">
                            <summary className={`pod-status pending ${(app.pods.pending || 0) > 0 ? 'has-pods' : ''}`}>
                              Pending: {app.pods.pending || 0} {(app.pods.pending || 0) > 0 ? '▼' : ''}
                            </summary>
                            {app.pods.pending_list && app.pods.pending_list.length > 0 ? (
                              <ul className="pod-list">
                                {app.pods.pending_list.map((pod, idx) => (
                                  <li key={idx} className="pod-item">
                                    <strong>{pod.name}</strong>
                                    {pod.reason && <span className="pod-reason"> • {pod.reason}</span>}
                                    {pod.owner && <span className="pod-owner"> ({pod.owner})</span>}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <div className="no-pods">No pending pods</div>
                            )}
                          </details>
                        </div>

                        {/* CrashLoop Pods Dropdown */}
                        <div className="pod-status-group">
                          <details className="pod-dropdown">
                            <summary className={`pod-status crashloop ${(app.pods.crashloop || 0) > 0 ? 'has-pods' : ''}`}>
                              CrashLoop: {app.pods.crashloop || 0} {(app.pods.crashloop || 0) > 0 ? '▼' : ''}
                            </summary>
                            {app.pods.crashloop_list && app.pods.crashloop_list.length > 0 ? (
                              <ul className="pod-list">
                                {app.pods.crashloop_list.map((pod, idx) => (
                                  <li key={idx} className="pod-item">
                                    <strong>{pod.name}</strong>
                                    {pod.reason && <span className="pod-reason"> • {pod.reason}</span>}
                                    {pod.restart_count !== undefined && <span className="pod-restarts"> • Restarts: {pod.restart_count}</span>}
                                    {pod.owner && <span className="pod-owner"> ({pod.owner})</span>}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <div className="no-pods">No crashloop pods</div>
                            )}
                          </details>
                        </div>

                        <div className="pod-status total">Total: {app.pods.total || 0}</div>
                      </div>
                    ) : (
                      <div className="no-data">No pod data</div>
                    )}
                  </div>

                  {/* Services */}
                  <div className="detail-section">
                    <h3>Services ({app.services?.length || 0})</h3>
                    {app.services && app.services.length > 0 ? (
                      app.services.map((svc, idx) => (
                        <div key={idx} className="detail-item">
                          <strong>{svc.name}</strong> ({svc.type})
                          <div>Cluster IP: {svc.cluster_ip || 'N/A'}</div>
                          {svc.external_ip && <div>External IP: {svc.external_ip}</div>}
                        </div>
                      ))
                    ) : (
                      <div className="no-data">No Services</div>
                    )}
                  </div>

                  {/* Databases */}
                  <div className="detail-section">
                    <h3>Databases</h3>
                    <div className="database-section">
                      <div>
                        <strong>PostgreSQL</strong>
                        {app.postgres_host || app.postgres?.host ? (
                          <div className="db-item">
                            <div className="db-connection">
                              <span className="db-label">Host:</span> {app.postgres_host || app.postgres?.host}
                              {(app.postgres_port || app.postgres?.port) && <span>:{(app.postgres_port || app.postgres?.port)}</span>}
                            </div>
                            {app.postgres_db && (
                              <div className="db-connection">
                                <span className="db-label">Database:</span> {app.postgres_db}
                              </div>
                            )}
                            {app.postgres_user && (
                              <div className="db-connection">
                                <span className="db-label">User:</span> {app.postgres_user}
                              </div>
                            )}
                            <div className="db-connection">
                              <span className="db-label">State:</span>
                              <span className={`db-state db-state-${postgresStatus}`}>
                                {postgresStatus === 'green' ? '🟢 Running' : 
                                 postgresStatus === 'yellow' ? '🟡 Starting' : 
                                 postgresStatus === 'red' ? '🔴 Stopped' : '⚪ Unknown'}
                              </span>
                            </div>
                            {(app.postgres_instance_id || app.postgres?.instance_id) && (
                              <div className="db-connection">
                                <span className="db-label">Instance ID:</span> {app.postgres_instance_id || app.postgres?.instance_id}
                              </div>
                            )}
                            {app.postgres?.is_shared && (
                              <div className="shared-resource-warning">
                                🔗 <strong>Shared Resource</strong>
                                {app.postgres?.shared_with && app.postgres.shared_with.length > 0 && (
                                  <div className="shared-with">
                                    Shared with: {app.postgres.shared_with.filter(a => a !== app.name && a !== app.app_name && a !== app.app).join(', ') || 'another application'}
                                  </div>
                                )}
                              </div>
                            )}
                            {/* DB Control Buttons - ALWAYS show when host exists */}
                            <div className="db-controls">
                              <button
                                className="start-button"
                                onClick={() => setDbControlModal({
                                  app: app,
                                  dbType: 'postgres',
                                  action: 'start'
                                })}
                                disabled={
                                  (postgresStatus === 'green' || postgresStatus === 'yellow') || 
                                  actionLoading[`${appId}-postgres-start`] ||
                                  !(app.postgres_instance_id || app.postgres?.instance_id)
                                }
                                title={
                                  !(app.postgres_instance_id || app.postgres?.instance_id) 
                                    ? 'Instance ID not available - cannot start' 
                                    : (postgresStatus === 'green' || postgresStatus === 'yellow')
                                      ? 'Database is already running'
                                      : ''
                                }
                              >
                                {actionLoading[`${appId}-postgres-start`] ? 'Starting...' : '▶ Start PostgreSQL'}
                              </button>
                              <button
                                className="stop-button"
                                onClick={() => setDbControlModal({
                                  app: app,
                                  dbType: 'postgres',
                                  action: 'stop'
                                })}
                                disabled={
                                  postgresStatus === 'red' || 
                                  actionLoading[`${appId}-postgres-stop`] ||
                                  !(app.postgres_instance_id || app.postgres?.instance_id)
                                }
                                title={
                                  !(app.postgres_instance_id || app.postgres?.instance_id) 
                                    ? 'Instance ID not available - cannot stop' 
                                    : postgresStatus === 'red'
                                      ? 'Database is already stopped'
                                      : ''
                                }
                              >
                                {actionLoading[`${appId}-postgres-stop`] ? 'Stopping...' : '⏹ Stop PostgreSQL'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="no-data">No PostgreSQL configuration found</div>
                        )}
                      </div>
                      <div>
                        <strong>Neo4j</strong>
                        {app.neo4j_host || app.neo4j?.host ? (
                          <div className="db-item">
                            <div className="db-connection">
                              <span className="db-label">Host:</span> {app.neo4j_host || app.neo4j?.host}
                              {(app.neo4j_port || app.neo4j?.port) && <span>:{(app.neo4j_port || app.neo4j?.port)}</span>}
                            </div>
                            {app.neo4j_username && (
                              <div className="db-connection">
                                <span className="db-label">Username:</span> {app.neo4j_username}
                              </div>
                            )}
                            <div className="db-connection">
                              <span className="db-label">State:</span>
                              <span className={`db-state db-state-${neo4jStatus}`}>
                                {neo4jStatus === 'green' ? '🟢 Running' : 
                                 neo4jStatus === 'yellow' ? '🟡 Starting' : 
                                 neo4jStatus === 'red' ? '🔴 Stopped' : '⚪ Unknown'}
                              </span>
                            </div>
                            {(app.neo4j_instance_id || app.neo4j?.instance_id) && (
                              <div className="db-connection">
                                <span className="db-label">Instance ID:</span> {app.neo4j_instance_id || app.neo4j?.instance_id}
                              </div>
                            )}
                            {app.neo4j?.is_shared && (
                              <div className="shared-resource-warning">
                                🔗 <strong>Shared Resource</strong>
                                {app.neo4j?.shared_with && app.neo4j.shared_with.length > 0 && (
                                  <div className="shared-with">
                                    Shared with: {app.neo4j.shared_with.filter(a => a !== app.name && a !== app.app_name && a !== app.app).join(', ') || 'another application'}
                                  </div>
                                )}
                              </div>
                            )}
                            {/* DB Control Buttons - ALWAYS show when host exists */}
                            <div className="db-controls">
                              <button
                                className="start-button"
                                onClick={() => setDbControlModal({
                                  app: app,
                                  dbType: 'neo4j',
                                  action: 'start'
                                })}
                                disabled={
                                  (neo4jStatus === 'green' || neo4jStatus === 'yellow') || 
                                  actionLoading[`${appId}-neo4j-start`] ||
                                  !(app.neo4j_instance_id || app.neo4j?.instance_id)
                                }
                                title={
                                  !(app.neo4j_instance_id || app.neo4j?.instance_id) 
                                    ? 'Instance ID not available - cannot start' 
                                    : (neo4jStatus === 'green' || neo4jStatus === 'yellow')
                                      ? 'Database is already running'
                                      : ''
                                }
                              >
                                {actionLoading[`${appId}-neo4j-start`] ? 'Starting...' : '▶ Start Neo4j'}
                              </button>
                              <button
                                className="stop-button"
                                onClick={() => setDbControlModal({
                                  app: app,
                                  dbType: 'neo4j',
                                  action: 'stop'
                                })}
                                disabled={
                                  neo4jStatus === 'red' || 
                                  actionLoading[`${appId}-neo4j-stop`] ||
                                  !(app.neo4j_instance_id || app.neo4j?.instance_id)
                                }
                                title={
                                  !(app.neo4j_instance_id || app.neo4j?.instance_id) 
                                    ? 'Instance ID not available - cannot stop' 
                                    : neo4jStatus === 'red'
                                      ? 'Database is already stopped'
                                      : ''
                                }
                              >
                                {actionLoading[`${appId}-neo4j-stop`] ? 'Stopping...' : '⏹ Stop Neo4j'}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="no-data">No Neo4j configuration found</div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Cost Tracking */}
                  <div className="detail-section">
                    <h3>Cost (Month-To-Date)</h3>
                    <div className="cost-section">
                      {app.cost_data ? (
                        <>
                          <div className="cost-display">
                            <div className="cost-row">
                              <span className="cost-label">Yesterday's Cost:</span>
                              <span className="cost-value-large">${(app.cost_data.yesterday_cost || 0).toFixed(2)}</span>
                            </div>
                            <div className="cost-row">
                              <span className="cost-label">Projected Monthly Cost:</span>
                              <span className="cost-value">${(app.cost_data.projected_monthly_cost || 0).toFixed(2)}</span>
                            </div>
                            <div className="cost-row">
                              <span className="cost-label">Daily Cost Today:</span>
                              <span className="cost-value">${(app.cost_data.daily_cost || 0).toFixed(2)}</span>
                            </div>
                          </div>
                          <button 
                            className="cost-button"
                            onClick={() => setCostModalApp(app)}
                          >
                            💰 View Cost Breakdown
                          </button>
                        </>
                      ) : (
                        <div className="cost-placeholder">
                          <p>Cost data will be available after the next cost tracking run (daily at 00:30 UTC)</p>
                          <button 
                            className="cost-button"
                            onClick={() => setCostModalApp(app)}
                          >
                            💰 View Cost Breakdown
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Schedule */}
                  <div className="detail-section">
                    <SchedulePanel 
                      app={app}
                      apiBaseUrl={apiBaseUrl}
                      getAuthToken={getAuthToken}
                      cognitoEnabled={COGNITO_ENABLED}
                    />
                  </div>

                  {/* Certificate Expiry */}
                  {app.certificate_expiry && (
                    <div className="detail-section">
                      <h3>Certificate Expiry</h3>
                      <div>{new Date(app.certificate_expiry).toLocaleString()}</div>
                    </div>
                  )}

                  {/* Shared Resources */}
                  {(app.shared_resources?.postgres?.length > 0 || 
                    app.shared_resources?.neo4j?.length > 0) && (
                    <div className="detail-section shared-warning">
                      <h3>⚠️ Shared Resources</h3>
                      {app.shared_resources.postgres?.map((pg, idx) => (
                        <div key={idx} className="shared-item">
                          PostgreSQL {pg.host || pg.instance_id || 'Unknown'} shared with: {pg.linked_apps?.join(', ')}
                        </div>
                      ))}
                      {app.shared_resources.neo4j?.map((neo, idx) => (
                        <div key={idx} className="shared-item">
                          Neo4j {neo.host || neo.instance_id || 'Unknown'} shared with: {neo.linked_apps?.join(', ')}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="detail-section">
                    <div className="metadata">
                      <div>Last Updated: {formatDate(app.last_updated)}</div>
                      {app.last_health_check && (
                        <div>Last Health Check: {formatDate(app.last_health_check)}</div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="app-actions">
              <button
                onClick={() => handleStart(appId)}
                disabled={finalStatus === 'UP' || actionLoading[appId]}
                className="btn btn-start"
              >
                {actionLoading[appId] === 'starting' ? 'Starting...' : '▶ Start Application'}
              </button>
              <button
                onClick={() => handleStop(appId)}
                disabled={finalStatus === 'DOWN' || actionLoading[appId]}
                className="btn btn-stop"
              >
                {actionLoading[appId] === 'stopping' ? 'Stopping...' : '⏹ Stop Application'}
              </button>
            </div>
          </div>
          )
        })}
      </div>

      {filteredAndSortedApps.length === 0 && !loading && (
        <div className="empty-state">
          <p>No applications found matching your filters.</p>
        </div>
      )}

      {apps.length === 0 && !loading && (
        <div className="empty-state">
          <p>No applications found. Run the discovery Lambda to populate the registry.</p>
        </div>
      )}

      {/* Cost Breakdown Modal */}
      {costModalApp && (
        <CostBreakdownModal
          app={costModalApp}
          isOpen={!!costModalApp}
          onClose={() => setCostModalApp(null)}
          apiBaseUrl={apiBaseUrl}
          getAuthToken={getAuthToken}
          cognitoEnabled={COGNITO_ENABLED}
        />
      )}

      {/* Database Control Modal */}
      {dbControlModal && (
        <DatabaseControlModal
          isOpen={!!dbControlModal}
          onClose={() => setDbControlModal(null)}
          onConfirm={async () => {
            const { app, dbType, action } = dbControlModal
            const appName = app.app_name || app.name || app.app
            const appId = getAppIdentifier(app)
            const loadingKey = `${appId}-${dbType}-${action}`
            
            setActionLoading(prev => ({ ...prev, [loadingKey]: true }))
            
            try {
              const headers = { 'Content-Type': 'application/json' }
              if (COGNITO_ENABLED) {
                try {
                  const token = await getAuthToken()
                  headers['Authorization'] = `Bearer ${token}`
                } catch (err) {
                  console.error('Failed to get auth token:', err)
                  setAuthenticated(false)
                  return
                }
              }
              
              const response = await fetch(`${apiBaseUrl}/db/${action}`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  app: appName,
                  type: dbType
                })
              })

              const data = await response.json()
              
              if (data.success) {
                alert(`✅ ${dbType === 'postgres' ? 'PostgreSQL' : 'Neo4j'} ${action === 'start' ? 'started' : 'stopped'} successfully!`)
                // Refresh app status
                fetchApps(false)
              } else {
                const errorMsg = data.reason || data.error || data.message || 'Unknown error'
                alert(`❌ Error: ${errorMsg}`)
              }
            } catch (err) {
              console.error(`Error during DB ${action}:`, err)
              alert(`❌ Error: ${err.message}`)
            } finally {
              setActionLoading(prev => ({ ...prev, [loadingKey]: false }))
              setDbControlModal(null)
            }
          }}
          app={dbControlModal.app}
          dbType={dbControlModal.dbType}
          action={dbControlModal.action}
        />
      )}
    </div>
  )
}

export default App
