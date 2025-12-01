import React from 'react'
import './CostBreakdownModal.css'

function CostBreakdownModal({ app, isOpen, onClose, apiBaseUrl, getAuthToken, cognitoEnabled }) {
  const [costData, setCostData] = React.useState(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState(null)

  React.useEffect(() => {
    if (isOpen && app) {
      fetchCostData()
    }
  }, [isOpen, app])

  const fetchCostData = async () => {
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

      const response = await fetch(`${apiBaseUrl}/apps/${app.app_name}/cost`, {
        method: 'GET',
        headers
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      setCostData(data)
    } catch (err) {
      console.error('Error fetching cost data:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value || 0)
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content cost-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Cost Breakdown: {app.app_name}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {loading && <div className="loading">Loading cost data...</div>}
          
          {error && (
            <div className="error-message">
              Error loading cost data: {error}
            </div>
          )}

          {costData && !loading && (
            <div className="cost-breakdown">
              <div className="cost-summary">
                <div className="cost-item highlight">
                  <label>Monthly Usage Cost (MTD):</label>
                  <span className="cost-value large">{formatCurrency(costData.mtd_cost || 0)}</span>
                </div>
                <div className="cost-item">
                  <label>Projected Monthly Cost:</label>
                  <span className="cost-value">{formatCurrency(costData.projected_monthly_cost || 0)}</span>
                </div>
                <div className="cost-item">
                  <label>Daily Cost Today:</label>
                  <span className="cost-value">{formatCurrency(costData.daily_cost || 0)}</span>
                </div>
                {costData.month && (
                  <div className="cost-item">
                    <label>Month:</label>
                    <span className="cost-value">{costData.month}</span>
                  </div>
                )}
                {costData.updated_at && (
                  <div className="cost-item">
                    <label>Last Updated:</label>
                    <span className="cost-value">{new Date(costData.updated_at).toLocaleString()}</span>
                  </div>
                )}
              </div>

              {costData.breakdown && Object.keys(costData.breakdown).length > 0 && (
                <div className="cost-details">
                  <h3>Cost Breakdown</h3>
                  <div className="breakdown-list">
                    <div className="breakdown-item">
                      <span className="breakdown-label">NodeGroups:</span>
                      <span className="breakdown-value">{formatCurrency(costData.breakdown.nodegroups || 0)}</span>
                    </div>
                    {(costData.breakdown.postgres_ec2 > 0 || costData.breakdown.postgres_ebs > 0) && (
                      <>
                        <div className="breakdown-item breakdown-subsection">
                          <span className="breakdown-label">PostgreSQL EC2:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.postgres_ec2 || 0)}</span>
                        </div>
                        <div className="breakdown-item breakdown-subsection">
                          <span className="breakdown-label">PostgreSQL EBS:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.postgres_ebs || 0)}</span>
                        </div>
                      </>
                    )}
                    {(costData.breakdown.neo4j_ec2 > 0 || costData.breakdown.neo4j_ebs > 0) && (
                      <>
                        <div className="breakdown-item breakdown-subsection">
                          <span className="breakdown-label">Neo4j EC2:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.neo4j_ec2 || 0)}</span>
                        </div>
                        <div className="breakdown-item breakdown-subsection">
                          <span className="breakdown-label">Neo4j EBS:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.neo4j_ebs || 0)}</span>
                        </div>
                      </>
                    )}
                    {/* Fallback to generic databases/ebs if detailed breakdown not available */}
                    {(!costData.breakdown.postgres_ec2 && !costData.breakdown.neo4j_ec2) && (
                      <>
                        <div className="breakdown-item">
                          <span className="breakdown-label">Databases:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.databases || 0)}</span>
                        </div>
                        <div className="breakdown-item">
                          <span className="breakdown-label">EBS Volumes:</span>
                          <span className="breakdown-value">{formatCurrency(costData.breakdown.ebs || 0)}</span>
                        </div>
                      </>
                    )}
                    <div className="breakdown-item">
                      <span className="breakdown-label">Network:</span>
                      <span className="breakdown-value">{formatCurrency(costData.breakdown.network || 0)}</span>
                    </div>
                  </div>
                </div>
              )}

              {costData.message && (
                <div className="info-message">
                  {costData.message}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

export default CostBreakdownModal

