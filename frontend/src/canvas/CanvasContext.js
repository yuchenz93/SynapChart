import { createContext } from 'react';

/**
 * Shared context between Canvas and BlockNode for the click-to-connect
 * pending connection state and port-click handler.
 *
 * Value shape: {
 *   pendingConnection: { sourceNodeId, sourcePortId, sourcePortType, sx, sy } | null,
 *   handlePortClick: (event, nodeId, portId, portType, direction) => void,
 * }
 */
export const CanvasContext = createContext(null);

/**
 * Client-side port compatibility heuristic — mirrors the backend validator.
 * Returns true if a connection from srcType to tgtType is valid.
 */
export function isCompatible(srcType, tgtType) {
  if (!srcType || !tgtType) return true;
  if (srcType === tgtType) return true;
  if (tgtType.endsWith('[any]') || srcType.endsWith('[any]')) return true;
  return srcType.split('[')[0] === tgtType.split('[')[0];
}
