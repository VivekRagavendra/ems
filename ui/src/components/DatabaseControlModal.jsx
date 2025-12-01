import React from 'react'
import './DatabaseControlModal.css'

function DatabaseControlModal({ isOpen, onClose, onConfirm, app, dbType, action }) {
  if (!isOpen) return null

  const dbName = dbType === 'postgres' ? 'PostgreSQL' : 'Neo4j'
  const appName = app?.app_name || app?.name || 'this application'
  const isShared = dbType === 'postgres' 
    ? app?.postgres?.is_shared 
    : app?.neo4j?.is_shared
  const sharedWith = dbType === 'postgres'
    ? app?.postgres?.shared_with?.filter(a => a !== appName)
    : app?.neo4j?.shared_with?.filter(a => a !== appName)

  const getMessage = () => {
    if (action === 'start') {
      return `Do you want to START the ${dbName} server for ${appName}?\n\nThis may take 1–3 minutes to become available.`
    } else {
      let msg = `Do you want to STOP the ${dbName} server for ${appName}?`
      if (isShared && sharedWith && sharedWith.length > 0) {
        msg += `\n\n⚠️ WARNING: This database is shared with other applications: ${sharedWith.join(', ')}.\n\nIf shared-protection is enabled, the stop will be blocked if any of these apps are still running.`
      }
      return msg
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content db-control-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>
            {action === 'start' ? '🚀 Start' : '🛑 Stop'} {dbName}
          </h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <div className="db-control-message">
            <pre>{getMessage()}</pre>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>
            Cancel
          </button>
          <button 
            className={`btn-confirm btn-${action}`}
            onClick={onConfirm}
          >
            {action === 'start' ? 'Start' : 'Stop'} {dbName}
          </button>
        </div>
      </div>
    </div>
  )
}

export default DatabaseControlModal


