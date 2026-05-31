#!/usr/bin/env node
/**
 * Frontend doctor script - verifies environment and dependencies.
 *
 * Checks:
 * - Node major version
 * - Required env vars
 * - Lockfile exists
 * - Next.js build compatibility
 */

import { readFileSync, existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = join(__dirname, '..');

let issues = [];
let warnings = [];

// Check Node version
const nodeVersion = process.version;
const nodeMajor = parseInt(nodeVersion.slice(1).split('.')[0]);
const requiredNodeMin = 20;
const requiredNodeMax = 22;

if (nodeMajor < requiredNodeMin) {
  issues.push(
    `Node version ${nodeVersion} is too old. Required: >=${requiredNodeMin}.<${requiredNodeMax + 1}`
  );
} else if (nodeMajor > requiredNodeMax) {
  warnings.push(
    `Node version ${nodeVersion} is newer than recommended range. Recommended: >=${requiredNodeMin}.<${requiredNodeMax + 1}`
  );
} else {
  console.log(`✓ Node version ${nodeVersion} is compatible`);
}

// Check lockfile
const lockfilePath = join(rootDir, 'package-lock.json');
if (!existsSync(lockfilePath)) {
  issues.push('package-lock.json not found. Run `npm install` to generate it.');
} else {
  console.log('✓ Lockfile exists');
}

// Check package.json
const packageJsonPath = join(rootDir, 'package.json');
if (!existsSync(packageJsonPath)) {
  issues.push('package.json not found');
} else {
  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8'));
    const engines = packageJson.engines;
    
    if (engines && engines.node) {
      console.log(`✓ package.json specifies Node engine: ${engines.node}`);
    }
    
    // Check for required dependencies
    const deps = packageJson.dependencies || {};
    if (!deps.next) {
      warnings.push('Next.js not found in dependencies');
    } else {
      console.log(`✓ Next.js version: ${deps.next}`);
    }
  } catch (error) {
    issues.push(`Failed to parse package.json: ${error.message}`);
  }
}

// Check .env file
const envPath = join(rootDir, '.env.local');
const envExamplePath = join(rootDir, '.env.example');
if (!existsSync(envPath) && !existsSync(envExamplePath)) {
  warnings.push('No .env.local or .env.example file found');
} else if (existsSync(envPath)) {
  console.log('✓ .env.local exists');
} else {
  warnings.push('.env.local not found (using .env.example as reference)');
}

// Check Next.js build compatibility
const nextConfigPath = join(rootDir, 'next.config.js');
if (!existsSync(nextConfigPath)) {
  warnings.push('next.config.js not found (may use default config)');
} else {
  console.log('✓ Next.js config exists');
}

// Report results
console.log('\n--- Frontend Doctor Report ---');

if (issues.length === 0 && warnings.length === 0) {
  console.log('✓ All checks passed');
  process.exit(0);
}

if (issues.length > 0) {
  console.log('\n❌ Issues:');
  issues.forEach(issue => console.log(`  - ${issue}`));
}

if (warnings.length > 0) {
  console.log('\n⚠ Warnings:');
  warnings.forEach(warning => console.log(`  - ${warning}`));
}

if (issues.length > 0) {
  console.log('\n❌ Doctor failed - fix issues before proceeding');
  process.exit(1);
} else {
  console.log('\n⚠ Doctor passed with warnings');
  process.exit(0);
}
