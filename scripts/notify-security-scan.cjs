const {createHash} = require('node:crypto');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');

const marker = '<!-- daily-security-checks -->';
const title = 'Daily security checks need attention';

function readJson(artifact, file) {
  const attempt = process.env.SECURITY_RUN_ATTEMPT;
  if (!/^[1-9][0-9]*$/.test(attempt)) {
    throw new Error('Invalid run attempt');
  }
  const directory = artifact.replace('daily-security-', `daily-security-${attempt}-`);
  return JSON.parse(readFileSync(join('security-reports', directory, file), 'utf8'));
}

function scanReport(name) {
  try {
    const report = readJson(name, 'trivy-results.sarif');
    if (report.version !== '2.1.0' || !Array.isArray(report.runs) || !report.runs.length) {
      throw new Error('Invalid SARIF report');
    }
    const findings = [];
    for (const run of report.runs) {
      if (run.tool?.driver?.name !== 'Trivy' || !Array.isArray(run.results) ||
          run.invocations?.some(item => item.executionSuccessful === false)) {
        throw new Error('Incomplete scanner invocation');
      }
      for (const result of run.results) {
        if (typeof result.ruleId !== 'string' || !result.ruleId || typeof result.message?.text !== 'string') {
          throw new Error('Invalid finding');
        }
        findings.push(JSON.stringify([
          result.ruleId, result.level, result.message.text,
          (result.locations || []).map(item => item.physicalLocation?.artifactLocation?.uri).sort(),
        ]));
      }
    }
    return {name, findings: [...new Set(findings)].sort()};
  } catch {
    return {name, error: 'Report missing, invalid or incomplete'};
  }
}

module.exports = async function notify({github, context, core}) {
  const branch = await github.rest.repos.getBranch({
    ...context.repo, branch: context.payload.repository.default_branch,
  });
  if (branch.data.commit.sha !== context.sha) {
    core.info('The default branch advanced; this revision cannot update the shared security issue.');
    return;
  }
  const needs = JSON.parse(process.env.SECURITY_JOB_RESULTS);
  const jobs = Object.fromEntries(['dependencies', 'images'].map(name => [name, needs[name]?.result || 'missing']));
  jobs.artifacts = process.env.SECURITY_DOWNLOAD_RESULT || 'missing';
  const reports = [scanReport('daily-security-dependencies')];
  try {
    const images = readJson('daily-security-inventory', 'image-matrix.json');
    if (!Array.isArray(images) || !images.length || images.some(item => !item.image || !item.category)) {
      throw new Error('Invalid image inventory');
    }
    reports.push(...images.map((_, index) => scanReport(`daily-security-image-${index}`)));
  } catch {
    reports.push({name: 'daily-security-inventory', error: 'Expected image inventory unavailable'});
  }
  const incomplete = reports.some(report => report.error) || jobs.artifacts !== 'success';
  const problem = incomplete || Object.values(jobs).some(result => result !== 'success') ||
    reports.some(report => report.findings?.length);
  const fingerprint = createHash('sha256').update(JSON.stringify({jobs, reports})).digest('hex');
  const signature = `<!-- daily-security-fingerprint:${fingerprint} -->`;
  const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const body = [
    marker, signature, '',
    problem ? 'Daily security checks found vulnerabilities or incomplete checks.' : 'All daily security checks passed.',
    '',
    ...Object.entries(jobs).map(([name, result]) => `- ${name}: ${result}`),
    ...reports.map(report => `- ${report.name}: ${report.error || `${report.findings.length} finding(s)`}`),
    '', `[Scan run and retained reports](${runUrl}).`,
    `[Latest daily runs](${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/workflows/daily-security.yml).`,
    'This scan checks repository inputs; it does not inspect the live fleet.',
  ].join('\n');

  const issues = await github.paginate(github.rest.issues.listForRepo, {
    ...context.repo, state: 'open', creator: 'github-actions[bot]', per_page: 100,
  });
  const issue = issues.find(item => !item.pull_request && item.title === title && item.body?.includes(marker));
  if (problem && !issue) {
    await github.rest.issues.create({...context.repo, title, body, assignees: [context.repo.owner]});
  } else if (issue && !issue.body.includes(signature)) {
    // Comments notify subscribers; a body edit alone does not reliably do so.
    await github.rest.issues.createComment({...context.repo, issue_number: issue.number, body});
    await github.rest.issues.update({
      ...context.repo, issue_number: issue.number, body,
      ...(problem ? {} : {state: 'closed', state_reason: 'completed'}),
    });
  } else {
    core.info('Security results unchanged; no issue write is needed.');
  }
  if (incomplete) {
    core.setFailed('Security scan evidence is incomplete; see the scan run and notification issue.');
  }
};
