import { useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, Outlines } from '@react-three/drei';
import * as THREE from 'three';

const geometries = [
  new THREE.BoxGeometry(1, 1, 1),
  new THREE.DodecahedronGeometry(0.7, 0),
  new THREE.IcosahedronGeometry(0.7, 0),
  new THREE.TetrahedronGeometry(0.8, 0),
  new THREE.CylinderGeometry(0.5, 0.5, 1, 12),
  new THREE.TorusGeometry(0.5, 0.2, 12, 16)
];

const NeoShape = ({ position, rotation, color, scale, geoIndex, speed }: any) => {
  return (
    <Float
      speed={speed} 
      rotationIntensity={2} 
      floatIntensity={2}
      position={position}
    >
      <mesh rotation={rotation} scale={scale} geometry={geometries[geoIndex]}>
        <meshBasicMaterial color={color} />
        <Outlines thickness={0.06} color="#000000" />
      </mesh>
    </Float>
  );
}

const Scene = () => {
  const group = useRef<THREE.Group>(null);
  
  useFrame((state) => {
    if (group.current) {
      group.current.rotation.y = state.clock.elapsedTime * 0.05;
      group.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.1) * 0.1;
    }
  });

  const colors = ['#FFF200', '#00FF66', '#00E5FF', '#FF3366', '#FF6600', '#FFFFFF']; 

  // Generate random shapes
  const shapes = useMemo(() => {
    return Array.from({ length: 30 }).map(() => ({
      position: [
        (Math.random() - 0.5) * 25,
        (Math.random() - 0.5) * 20,
        (Math.random() - 0.5) * 10 - 2
      ],
      rotation: [
        Math.random() * Math.PI,
        Math.random() * Math.PI,
        Math.random() * Math.PI
      ],
      scale: 0.5 + Math.random() * 1.5,
      color: colors[Math.floor(Math.random() * colors.length)],
      geoIndex: Math.floor(Math.random() * geometries.length),
      speed: 1 + Math.random() * 2
    }));
  }, []);

  return (
    <group ref={group}>
      {shapes.map((props, i) => (
        <NeoShape key={i} {...props} />
      ))}
    </group>
  );
};

export const ThreeScene = () => {
  return (
    <Canvas 
      camera={{ position: [0, 0, 10], fov: 45 }}
      style={{ background: '#F4F4F0' }}
    >
      <Scene />
    </Canvas>
  );
};
