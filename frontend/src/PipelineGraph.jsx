import React, { useEffect, useState } from 'react';
import ReactFlow from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';

const PipelineGraph = () => {
  const [nodes, setNodes] = useState([]);

  useEffect(() => {
    axios.get('/api/pipeline/graph').then(res => {
      const { nodes: nodeNames, current } = res.data;
      const initialNodes = nodeNames.map((name, index) => ({
        id: name,
        data: { label: name },
        position: { x: index * 150, y: 50 },
        style: { background: name === current ? '#68f' : '#ddd', color: '#fff' }
      }));
      setNodes(initialNodes);
    });
  }, []);

  return <div style={{ height: '200px', width: '100%' }}><ReactFlow nodes={nodes} /></div>;
};

export default PipelineGraph;