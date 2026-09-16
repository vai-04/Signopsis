import { useEffect, useRef, useState } from "react";

/** Mounts children the first time the placeholder gets near the viewport (keeps WebGL contexts and sockets lazy). */
export function LazyMount({ children, minHeight = 400, className = "", rootMargin = "300px" }) {
  const ref = useRef(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (on) return undefined;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setOn(true); }, { rootMargin });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [on, rootMargin]);
  return (
    <div ref={ref} className={className} style={on ? undefined : { minHeight }}>
      {on ? children : <div className="h-full w-full animate-pulse rounded-[1.8rem] bg-white/60" style={{ minHeight }} />}
    </div>
  );
}

export function Reveal({ children, className = "", delay = 0, as: Tag = "div" }) {
  return <Tag className={className} data-reveal style={{ "--d": `${delay}s` }}>{children}</Tag>;
}
