targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string

@description('JWT secret for admin tokens')
@secure()
param jwtSecret string

@description('Whether to enable admin review endpoints (default: false for security)')
param enableAdminReview bool = false

@description('Whether to enable admin import endpoints (default: false for security)')
param enableAdminImports bool = false

@description('CORS allowed origins - must be explicit HTTPS URL, no wildcards')
param corsOrigins string = ''  // e.g., "https://frontend.example.com"

@description('Container Apps CPU cores')
param containerCpu string = '0.5'

@description('Container Apps memory')
param containerMemory string = '1Gi'

@description('PostgreSQL SKU tier')
param postgresSkuTier string = 'Burstable'

@description('PostgreSQL SKU name')
param postgresSkuName string = 'Standard_B1ms'

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: { 'azd-env-name': environmentName }
}

// Container Registry
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'containerRegistry'
  scope: rg
  params: {
    name: 'cr${uniqueString(rg.id)}'
    location: location
  }
}

// Log Analytics workspace for monitoring
module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'logAnalytics'
  scope: rg
  params: {
    name: 'law-${environmentName}'
    location: location
  }
}

// Container Apps Environment
module containerAppsEnvironment 'modules/container-apps-env.bicep' = {
  name: 'containerAppsEnvironment'
  scope: rg
  params: {
    name: 'cae-${environmentName}'
    location: location
    logAnalyticsWorkspaceId: logAnalytics.outputs.id
  }
}

// PostgreSQL Flexible Server with PostGIS
module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  scope: rg
  params: {
    name: 'psql-${environmentName}'
    location: location
    administratorLogin: 'jtaadmin'
    administratorPassword: postgresAdminPassword
    skuTier: postgresSkuTier
    skuName: postgresSkuName
  }
}

// Backend Container App
module backendApp 'modules/backend-app.bicep' = {
  name: 'backendApp'
  scope: rg
  params: {
    name: 'ca-backend-${environmentName}'
    location: location
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.id
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    databaseHost: postgres.outputs.fqdn
    databaseName: 'judgetracker'
    databaseUser: 'jtaadmin'
    databasePassword: postgresAdminPassword
    jwtSecret: jwtSecret
    enableAdminReview: enableAdminReview
    enableAdminImports: enableAdminImports
    corsOrigins: corsOrigins
    cpu: containerCpu
    memory: containerMemory
  }
}

// Frontend Container App
module frontendApp 'modules/frontend-app.bicep' = {
  name: 'frontendApp'
  scope: rg
  params: {
    name: 'ca-frontend-${environmentName}'
    location: location
    containerAppsEnvironmentId: containerAppsEnvironment.outputs.id
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    // Use HTTPS backend URL - required for production
    nextPublicApiBaseUrl: 'https://${backendApp.outputs.fqdn}'
    backendInternalUrlParam: 'https://${backendApp.outputs.fqdn}'  // Can be internal URL if using VNet
    cpu: containerCpu
    memory: containerMemory
  }
}

// Outputs for azd
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name
output BACKEND_URL string = backendApp.outputs.url
output FRONTEND_URL string = frontendApp.outputs.url
output POSTGRES_HOST string = postgres.outputs.fqdn
output POSTGRES_DATABASE string = 'judgetracker'
