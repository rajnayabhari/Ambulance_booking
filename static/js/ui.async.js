// === Async, low-refresh UI helpers ===
// - Lazy-load media with IntersectionObserver
// - Defer non-critical work via requestIdleCallback (or setTimeout)
// - Prefetch links on hover/touch
// - Use View Transitions if available for smoother UI without reflow storms

(function(){
  const on = (el, ev, fn, opts) => el.addEventListener(ev, fn, opts);

  // Progressive enhancement flag
  document.documentElement.classList.add('js');

  // IntersectionObserver for lazy images
  const lazyIO = 'IntersectionObserver' in window ? new IntersectionObserver((entries)=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting){
        const img = entry.target;
        const src = img.getAttribute('data-src');
        if(src){
          img.src = src;
          img.onload = ()=> img.setAttribute('data-loaded','true');
          img.removeAttribute('data-src');
        }
        lazyIO.unobserve(img);
      }
    });
  }, { rootMargin: '200px 0px' }) : null;

  document.querySelectorAll('img.lazy[data-src]').forEach(img=>{
    if(lazyIO){ lazyIO.observe(img); }
    else { // fallback
      img.src = img.getAttribute('data-src'); img.onload = ()=> img.setAttribute('data-loaded','true');
    }
  });

  // requestIdleCallback polyfill
  const ric = window.requestIdleCallback || function(cb){ return setTimeout(()=>cb({didTimeout:true,timeRemaining:()=>0}), 1); };

  // Defer non-critical tasks
  ric(()=>{
    // Preconnects (WhatsApp / maps / cdns etc.) — update as needed
    const links = [
      'https://web.whatsapp.com', 'https://wa.me', 'https://maps.googleapis.com'
    ];
    links.forEach(href=>{
      const l = document.createElement('link');
      l.rel = 'preconnect'; l.href = href; l.crossOrigin = '';
      document.head.appendChild(l);
    });
  });

  // Link prefetch on hover/touchstart
  const canPrefetch = 'relList' in HTMLLinkElement.prototype && HTMLLinkElement.prototype.relList.supports && HTMLLinkElement.prototype.relList.supports('prefetch');
  if(canPrefetch){
    const prefetch = (url)=>{
      const l = document.createElement('link');
      l.rel = 'prefetch'; l.href = url; l.as = 'document';
      document.head.appendChild(l);
    };
    on(document, 'mouseover', (e)=>{
      const a = e.target.closest('a[href^="/"], a[href^="./"]');
      if(a) prefetch(a.href);
    }, {passive:true});
    on(document, 'touchstart', (e)=>{
      const a = e.target.closest('a[href^="/"], a[href^="./"]');
      if(a) prefetch(a.href);
    }, {passive:true});
  }

  // Bottom sheet toggles
  const sheet = document.querySelector('.sheet');
  const openers = document.querySelectorAll('[data-open-sheet]');
  const closers = document.querySelectorAll('[data-close-sheet]');
  openers.forEach(b=> on(b,'click',()=> sheet?.classList.add('open')));
  closers.forEach(b=> on(b,'click',()=> sheet?.classList.remove('open')));

  // View Transitions API (safe fallback)
  function transition(updateFn){
    if(document.startViewTransition){
      document.startViewTransition(()=>{ updateFn(); });
    }else{
      updateFn();
    }
  }

  // Example: tab switch without layout thrash
  document.querySelectorAll('.tabs').forEach(tabs=>{
    tabs.addEventListener('click', (e)=>{
      const el = e.target.closest('.tab');
      if(!el) return;
      const group = el.parentElement;
      const target = el.getAttribute('data-target');
      transition(()=>{
        group.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t===el));
        document.querySelectorAll('[data-panel]').forEach(p=>{
          p.classList.toggle('hide', p.getAttribute('data-panel') !== target);
        });
      });
    });
  });

  // Adapt animations if connection is slow
  try{
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if(conn && (conn.saveData || (conn.effectiveType && /2g/.test(conn.effectiveType)))){
      document.documentElement.style.setProperty('--shadow-lg','0 6px 16px rgba(0,0,0,.25)');
    }
  }catch{}

  // Debounced resize handler (avoid layout thrashing)
  let rId;
  on(window,'resize',()=>{
    cancelAnimationFrame(rId);
    rId = requestAnimationFrame(()=>{
      // cheap layout updates here
      document.documentElement.style.setProperty('--vh', `${window.innerHeight*0.01}px`);
    });
  });

})();