import axios from 'axios';

// Use relative URLs so the app works regardless of host/port.
// In dev (Vite proxy), /api is forwarded to localhost:8000.
// In production (served by uvicorn), /api hits the same server.
const BASE = '';

export const getBlocks = () =>
  axios.get(`${BASE}/api/blocks/`).then(r => r.data);

export const validateConnection = (outputType, inputType) =>
  axios.post(`${BASE}/api/blocks/validate-connection`, { output_type: outputType, input_type: inputType });

export const runPipeline = (workflow, useCache = true) =>
  axios.post(`${BASE}/api/pipeline/${useCache ? 'run-from-cache' : 'run'}`, { workflow });

export const stepPipeline = (workflow, nodeId) =>
  axios.post(`${BASE}/api/pipeline/step`, { workflow, node_id: nodeId });

export const stopPipeline = () =>
  axios.post(`${BASE}/api/pipeline/stop`);

export const saveWorkflow = (workflow, filePath) =>
  axios.post(`${BASE}/api/files/save`, { workflow, file_path: filePath });

export const loadWorkflow = (filePath) =>
  axios.post(`${BASE}/api/files/load`, { file_path: filePath });

export const getTemplates = () =>
  axios.get(`${BASE}/api/files/templates`).then(r => r.data);

export const loadTemplate = (category, name) =>
  axios.get(`${BASE}/api/files/templates/${category}/${name}`).then(r => r.data);

export const browseFiles = (path = '') =>
  axios.get(`${BASE}/api/files/browse`, { params: { path } }).then(r => r.data);

export const getBlockSource = (blockTypeId) =>
  axios.get(`${BASE}/api/blocks/${blockTypeId}/source`).then(r => r.data);

export const registerCustomBlock = (sourceCode) =>
  axios.post(`${BASE}/api/blocks/register-custom`, { source_code: sourceCode }).then(r => r.data);

export const createBlock         = (data) => axios.post(`${BASE}/api/blocks/create`, data).then(r => r.data);
export const updateBlock         = (id, data) => axios.put(`${BASE}/api/blocks/${id}`, data).then(r => r.data);
export const updateBlockCategory = (id, category) => axios.patch(`${BASE}/api/blocks/${id}/category`, { category }).then(r => r.data);
export const deleteBlock         = (id) => axios.delete(`${BASE}/api/blocks/${id}`).then(r => r.data);
export const testRunBlock        = (data) => axios.post(`${BASE}/api/blocks/test-run`, data).then(r => r.data);
export const registerLocalBlocks = (localBlocks) =>
  axios.post(`${BASE}/api/blocks/register-local`, { local_blocks: localBlocks }).then(r => r.data);

export const clearCache = (nodeId = null) =>
  axios.post(`${BASE}/api/pipeline/clear-cache`, { node_id: nodeId }).then(r => r.data);

export const packageBlock          = (data) => axios.post(`${BASE}/api/blocks/package`, data).then(r => r.data);
export const saveLocalToLibrary    = (blockDef, libraryId) =>
  axios.post(`${BASE}/api/blocks/save-local-to-library`, { block_def: blockDef, library_id: libraryId }).then(r => r.data);
export const listCompositeBlocks = () => axios.get(`${BASE}/api/blocks/composite/`).then(r => r.data);
export const getCompositeBlock   = (id) => axios.get(`${BASE}/api/blocks/composite/${id}`).then(r => r.data);
export const deleteCompositeBlock  = (id) => axios.delete(`${BASE}/api/blocks/composite/${id}`).then(r => r.data);
export const updateCompositeBlock  = (id, definition) => axios.put(`${BASE}/api/blocks/composite/${id}`, definition).then(r => r.data);

// Library management
export const getLibraries      = () => axios.get(`${BASE}/api/libraries/`).then(r => r.data);
export const getLibrary        = (id) => axios.get(`${BASE}/api/libraries/${id}`).then(r => r.data);
export const refreshLibraries  = () => axios.post(`${BASE}/api/libraries/refresh`).then(r => r.data);
export const moveBlock         = (blockTypeId, targetLibraryId) =>
  axios.post(`${BASE}/api/libraries/move-block`, { block_type_id: blockTypeId, target_library_id: targetLibraryId }).then(r => r.data);
export const getLibraryConflicts = (libraryIds) =>
  axios.get(`${BASE}/api/libraries/conflicts`, { params: { library_ids: libraryIds.join(',') } }).then(r => r.data);

// Pack / extract
export const packWorkflow    = (workflow, filePath) =>
  axios.post(`${BASE}/api/files/pack`, { workflow, file_path: filePath }).then(r => r.data);
export const extractBlock    = (packedWorkflowPath, blockTypeId, targetLibraryId) =>
  axios.post(`${BASE}/api/files/extract-block`, {
    packed_workflow_path: packedWorkflowPath,
    block_type_id: blockTypeId,
    target_library_id: targetLibraryId,
  }).then(r => r.data);

// Debug / workspace endpoints
export const setBreakpoint = (nodeId) =>
  axios.post(`${BASE}/api/debug/breakpoint/set`, null, { params: { node_id: nodeId } });

export const clearBreakpoint = (nodeId) =>
  axios.post(`${BASE}/api/debug/breakpoint/clear`, null, { params: { node_id: nodeId } });

export const clearAllBreakpoints = () =>
  axios.post(`${BASE}/api/debug/breakpoint/clear-all`);

export const continueExecution = () =>
  axios.post(`${BASE}/api/debug/continue`);

export const getWorkspaceNode = (nodeId) =>
  axios.get(`${BASE}/api/debug/workspace/${nodeId}`).then(r => r.data);

export const getVariableDetail = (nodeId, portId) =>
  axios.get(`${BASE}/api/debug/workspace/${nodeId}/${portId}/detail`).then(r => r.data);

export const getVariablePreview = (nodeId, portId) =>
  axios.get(`${BASE}/api/debug/workspace/${nodeId}/${portId}/preview`).then(r => r.data);

export const openLogsSocket = (onMessage) => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${window.location.host}/api/pipeline/logs`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
};
