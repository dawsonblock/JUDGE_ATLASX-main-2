metadata description = 'Backend FastAPI Container App'

param name string
param location string = resourceGroup().location
param containerAppsEnvironmentId string
param containerRegistryLoginServer string

// Database configuration
param databaseHost string
param databaseName string
param databaseUser string
@secure()
param databasePassword string

// App configuration - SECURE DEFAULTS
@secure()
param jwtSecret string
param enableAdminReview bool = false  // Disabled by default for security
param enableAdminImports bool = false  // Disabled by default for security
param cpu string = '0.5'
param memory string = '1Gi'

// CORS configuration - must be explicit HTTPS URL, no wildcards
param corsOrigins string = ''  // e.g., "https://frontend.example.com"

// Container image tag (set by azd during deploy)
param imageTag string = 'latest'

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistryLoginServer
          username: listCredentials(resourceId('Microsoft.ContainerRegistry/registries', split(containerRegistryLoginServer, '.')[0]), '2023-07-01').username
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: [
        {
          name: 'database-password'
          value: databasePassword
        }
        {
          name: 'database-url'
          value: 'postgresql+psycopg://${databaseUser}:${databasePassword}@${databaseHost}:5432/${databaseName}'
        }
        {
          name: 'jwt-secret'
          value: jwtSecret
        }
        {
          name: 'registry-password'
          value: listCredentials(resourceId('Microsoft.ContainerRegistry/registries', split(containerRegistryLoginServer, '.')[0]), '2023-07-01').passwords[0].value
        }
        {
          name: 'admin-token'
          value: jwtSecret
        }
        {
          name: 'admin-review-token'
          value: jwtSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: '${containerRegistryLoginServer}/backend:${imageTag}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            {
              name: 'JTA_DATABASE_URL'
              secretRef: 'database-url'  // Use secretRef for sensitive connection string
            }
            {
              name: 'JTA_CORS_ORIGINS'
              value: corsOrigins  // Must be explicit HTTPS URL, no wildcards allowed
            }
            {
              name: 'JTA_ENABLE_ADMIN_REVIEW'
              value: string(enableAdminReview)
            }
            {
              name: 'JTA_ENABLE_ADMIN_IMPORTS'
              value: string(enableAdminImports)
            }
            {
              name: 'JTA_ADMIN_TOKEN'
              secretRef: 'admin-token'
            }
            {
              name: 'JTA_ADMIN_REVIEW_TOKEN'
              secretRef: 'admin-review-token'
            }
            {
              name: 'PORT'
              value: '8000'
            }
            {
              name: 'PYTHONUNBUFFERED'
              value: '1'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            custom: {
              type: 'http'
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = backendApp.id
output name string = backendApp.name
output fqdn string = backendApp.properties.configuration.ingress.fqdn
output url string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
