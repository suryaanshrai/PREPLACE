/**
 * LinkedIn job search subprocess worker.
 * Usage: node search.js '<json_params>'
 * Reads search parameters from process.argv[2] as a JSON string,
 * queries LinkedIn, and prints the result JSON to stdout.
 * Always sets dateSincePosted: "past month" and sortBy: "recent".
 */

// Redirect all console.* to stderr so npm package debug/info logs
// don't corrupt the JSON written to stdout by this script.
console.log = (...a) => process.stderr.write(a.join(' ') + '\n');
console.warn = (...a) => process.stderr.write('[WARN] ' + a.join(' ') + '\n');
console.error = (...a) => process.stderr.write('[ERR] ' + a.join(' ') + '\n');
console.info = (...a) => process.stderr.write('[INFO] ' + a.join(' ') + '\n');

const linkedIn = require('linkedin-jobs-api');

const raw = process.argv[2];
if (!raw) {
  process.stdout.write(JSON.stringify({ error: 'No query params provided', jobs: [] }));
  process.exit(0);
}

let params;
try {
  params = JSON.parse(raw);
} catch (e) {
  process.stdout.write(JSON.stringify({ error: 'Invalid JSON params: ' + e.message, jobs: [] }));
  process.exit(0);
}

// Enforce recency filter and sensible defaults
const queryOptions = {
  keyword: params.keyword || '',
  location: params.location || '',
  dateSincePosted: 'past month',
  sortBy: 'recent',
  limit: String(params.limit || '10'),
  page: '0',
};

if (params.jobType) queryOptions.jobType = params.jobType;
if (params.remoteFilter) queryOptions.remoteFilter = params.remoteFilter;
if (params.experienceLevel) queryOptions.experienceLevel = params.experienceLevel;

linkedIn.query(queryOptions)
  .then(jobs => {
    process.stdout.write(JSON.stringify({ jobs: jobs || [], search_params: queryOptions }));
  })
  .catch(err => {
    process.stdout.write(JSON.stringify({ error: err.message || 'LinkedIn query failed', jobs: [] }));
  });
