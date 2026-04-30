import { getBezierPath } from 'reactflow';

/**
 * Custom connection line rendered while the user is dragging a new edge.
 *
 * @param {object} props - React Flow connection line props.
 */
export default function ConnectionLine({
  fromX, fromY, fromPosition,
  toX, toY, toPosition,
  connectionLineStyle,
}) {
  const [edgePath] = getBezierPath({ sourceX: fromX, sourceY: fromY, sourcePosition: fromPosition, targetX: toX, targetY: toY, targetPosition: toPosition });

  return (
    <g>
      <path
        fill="none"
        stroke="#6366f1"
        strokeWidth={2}
        strokeDasharray="6 3"
        d={edgePath}
        style={connectionLineStyle}
      />
      <circle cx={toX} cy={toY} r={4} fill="#6366f1" />
    </g>
  );
}
