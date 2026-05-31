metadata description = 'Frontend Next.js Container App'

param name string
param location string = resourceGroup().location
param containerAppsEnvironmentId string
param containerRegistryLoginServer string
@description('DEPRECATED: Use nextPublicApiBaseUrl and backendInternalUrlParam instead')
param backendInternalUrl string = ''

param cpu string = '0.5'
param memory string = '1Gi'
param imageTag string = 'latest'

// Backend URLs - must be explicit HTTPS URLs (no wildcards, no HTTP in production)
@description('Public HTTPS backend URL for browser API calls')
param nextPublicApiBaseUrl string  // e.g., https://backend.example.com

@description('Internal backend URL for server-side calls (can use internal networking)')
param backendInternalUrlParam string = ''  // Defaults to nextPublicApiBaseUrl if empty

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
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
          name: 'registry-password'
          value: listCredentials(resourceId('Microsoft.ContainerRegistry/registries', split(containerRegistryLoginServer, '.')[0]), '2023-07-01').passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: '${containerRegistryLoginServer}/frontend:${imageTag}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            {
              name: 'NEXT_PUBLIC_API_BASE_URL'
              // Use new param if provided, fall back to deprecated param for compatibility
              value: empty(backendInternalUrl) ? nextPublicApiBaseUrl : backendInternalUrl
            }
            {
              name: 'BACKEND_INTERNAL_URL'
              // Use explicit internal URL if provided, otherwise use public URL
              value: empty(backendInternalUrlParam) 
                ? (empty(backendInternalUrl) ? nextPublicApiBaseUrl : backendInternalUrl)
                : backendInternalUrlParam
            }
            {
              name: 'PORT'
              value: '3000'
            }
            {
              name: 'NODE_ENV'
              value: 'production'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 3000
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/'
                port: 3000
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

output id string = frontendApp.id
output name string = frontendApp.name
output fqdn string = frontendApp.properties.configuration.ingress.fqdn
output url string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
