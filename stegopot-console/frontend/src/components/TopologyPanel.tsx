import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import { Bot, Inbox, ScanSearch, Send } from "lucide-react";
import type { MessageView, NodeView, TopologyView } from "../types/contracts";

interface TopologyPanelProps {
  topology: TopologyView;
  selectedMessage?: MessageView;
}

type AgentGraphNode = Node<{
  node: NodeView;
  active: boolean;
}, "agent">;

/** 根据节点角色选择明确的操作图标。 */
function roleIcon(role: string) {
  const normalized = role.toLocaleLowerCase();
  if (normalized.includes("sender")) return <Send size={15} />;
  if (normalized.includes("receiver")) return <Inbox size={15} />;
  if (normalized.includes("auditor")) return <ScanSearch size={15} />;
  return <Bot size={15} />;
}

/** React Flow 使用的智能体节点外观。 */
function AgentNode({ data }: NodeProps<AgentGraphNode>) {
  const { node, active } = data;
  return (
    <div className={`graph-node ${active ? "is-active" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <span className="graph-node-icon">{roleIcon(node.role)}</span>
      <span className="graph-node-copy">
        <strong>{node.label}</strong>
        <small>{node.id}</small>
      </span>
      <span className="graph-node-count">{node.sent_count}/{node.received_count}</span>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode } satisfies NodeTypes;

/** 将后端拓扑投影为稳定的横向图布局。 */
function buildNodes(
  topology: TopologyView,
  selectedMessage?: MessageView,
): AgentGraphNode[] {
  const columns = Math.min(3, Math.max(1, topology.nodes.length));
  return topology.nodes.map((node, index) => ({
    id: node.id,
    type: "agent",
    position: {
      x: (index % columns) * 230,
      y: Math.floor(index / columns) * 130 + (index % 2 === 1 ? 34 : 0),
    },
    data: {
      node,
      active:
        selectedMessage?.sender === node.id ||
        selectedMessage?.recipient === node.id,
    },
    draggable: true,
  }));
}

/** 显示当前实验通信拓扑并高亮所选消息路径。 */
export function TopologyPanel({ topology, selectedMessage }: TopologyPanelProps) {
  const nodes = useMemo(
    () => buildNodes(topology, selectedMessage),
    [selectedMessage, topology],
  );
  const edges = useMemo<Edge[]>(
    () =>
      topology.edges.map((edge) => {
        const active =
          edge.source === selectedMessage?.sender &&
          edge.target === selectedMessage?.recipient;
        return {
          ...edge,
          type: "smoothstep",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: active ? "#b54708" : "#6f7d77",
          },
          style: {
            stroke: active ? "#b54708" : "#6f7d77",
            strokeWidth: active ? 2.4 : 1.4,
          },
        };
      }),
    [selectedMessage, topology.edges],
  );

  return (
    <section className="panel topology-panel">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">NETWORK</span>
          <h2>通信拓扑</h2>
        </div>
        <span className="panel-count">
          {topology.nodes.length} 节点 · {topology.edges.length} 条边
        </span>
      </div>
      <div className="topology-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.24 }}
          minZoom={0.55}
          maxZoom={1.45}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#d6ddda" gap={24} size={1} />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </section>
  );
}
