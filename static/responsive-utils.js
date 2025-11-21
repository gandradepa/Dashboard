/**
 * ============================================
 * RESPONSIVE DESIGN UTILITIES - JAVASCRIPT
 * ============================================
 * Handles viewport detection, zoom handling, 
 * orientation changes, and dynamic layout adaptations
 */

(function() {
  'use strict';

  // ============================================
  // 1. VIEWPORT DETECTION & TRACKING
  // ============================================

  const ResponsiveManager = {
    // Current viewport state - initialized in init() to avoid 'this' binding issues
    viewportState: {
      width: window.innerWidth,
      height: window.innerHeight,
      isMobile: window.innerWidth < 576,
      isTablet: window.innerWidth >= 576 && window.innerWidth < 992,
      isDesktop: window.innerWidth >= 992,
      isSmallDesktop: window.innerWidth >= 992 && window.innerWidth < 1200,
      isLargeDesktop: window.innerWidth >= 1200,
      is4K: window.innerWidth >= 1920,
      pixelRatio: window.devicePixelRatio || 1,
      orientation: window.innerHeight > window.innerWidth ? 'portrait' : 'landscape',
      zoomLevel: Math.round((window.devicePixelRatio * 100)),
      isRetina: window.devicePixelRatio >= 2,
      isTouch: false,        // Will be set in init()
      connection: 'unknown', // Will be set in init()
    },

    // Event listeners array
    listeners: [],

    /**
     * Initialize responsive manager
     */
    init: function() {
      // NOW set properties that depend on methods
      this.viewportState.isTouch = this.detectTouch();
      this.viewportState.connection = this.detectConnectionSpeed();
      
      console.log('ResponsiveManager initialized:', this.viewportState);
      
      // Set up event listeners
      window.addEventListener('resize', this.onResize.bind(this), { passive: true });
      window.addEventListener('orientationchange', this.onOrientationChange.bind(this), { passive: true });
      document.addEventListener('visibilitychange', this.onVisibilityChange.bind(this), { passive: true });
      
      // Handle zoom changes (debounced)
      window.addEventListener('wheel', this.debounce(this.onZoomChange.bind(this), 500), { passive: true });
      
      // Apply initial responsive adjustments
      this.applyResponsiveAdjustments();
      
      // Mark document as JS-enabled for responsive enhancements
      document.documentElement.classList.add('js-enabled');
      
      // Add viewport class for CSS hooks
      this.updateViewportClass();
    },

    /**
     * Detect touch capability
     */
    detectTouch: function() {
      return (('ontouchstart' in window) ||
              (navigator.maxTouchPoints > 0) ||
              (navigator.msMaxTouchPoints > 0));
    },

    /**
     * Detect network connection speed
     */
    detectConnectionSpeed: function() {
      const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (!connection) return 'unknown';
      
      const effectiveType = connection.effectiveType;
      return effectiveType || 'unknown';
    },

    /**
     * Debounce function for performance
     */
    debounce: function(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    },

    /**
     * Handle window resize
     */
    onResize: function() {
      const newWidth = window.innerWidth;
      const newHeight = window.innerHeight;
      
      // Only update if size actually changed
      if (newWidth !== this.viewportState.width || newHeight !== this.viewportState.height) {
        this.updateViewportState(newWidth, newHeight);
        this.applyResponsiveAdjustments();
        this.triggerListeners('resize', this.viewportState);
      }
    },

    /**
     * Handle orientation change
     */
    onOrientationChange: function() {
      const orientation = window.innerHeight > window.innerWidth ? 'portrait' : 'landscape';
      
      if (orientation !== this.viewportState.orientation) {
        this.viewportState.orientation = orientation;
        document.documentElement.setAttribute('data-orientation', orientation);
        this.triggerListeners('orientationchange', this.viewportState);
      }
    },

    /**
     * Handle visibility change (tab focus)
     */
    onVisibilityChange: function() {
      if (document.hidden) {
        this.triggerListeners('hide', this.viewportState);
      } else {
        // Recalculate on tab focus (in case window was resized)
        this.onResize();
        this.triggerListeners('show', this.viewportState);
      }
    },

    /**
     * Detect zoom level changes
     */
    onZoomChange: function() {
      const currentZoom = Math.round((window.devicePixelRatio * 100));
      
      if (currentZoom !== this.viewportState.zoomLevel) {
        this.viewportState.zoomLevel = currentZoom;
        console.log('Zoom level changed to:', currentZoom + '%');
        this.triggerListeners('zoom', this.viewportState);
      }
    },

    /**
     * Update viewport state
     */
    updateViewportState: function(width, height) {
      this.viewportState.width = width;
      this.viewportState.height = height;
      this.viewportState.isMobile = width < 576;
      this.viewportState.isTablet = width >= 576 && width < 992;
      this.viewportState.isDesktop = width >= 992;
      this.viewportState.isSmallDesktop = width >= 992 && width < 1200;
      this.viewportState.isLargeDesktop = width >= 1200;
      this.viewportState.is4K = width >= 1920;
      this.updateViewportClass();
    },

    /**
     * Update viewport class on document element
     */
    updateViewportClass: function() {
      const doc = document.documentElement;
      
      doc.classList.remove('viewport-xs', 'viewport-sm', 'viewport-md', 'viewport-lg', 'viewport-xl', 'viewport-2xl');
      
      if (this.viewportState.is4K) {
        doc.classList.add('viewport-2xl');
      } else if (this.viewportState.isLargeDesktop) {
        doc.classList.add('viewport-xl');
      } else if (this.viewportState.isSmallDesktop) {
        doc.classList.add('viewport-lg');
      } else if (this.viewportState.isDesktop) {
        doc.classList.add('viewport-md');
      } else if (this.viewportState.isTablet) {
        doc.classList.add('viewport-sm');
      } else {
        doc.classList.add('viewport-xs');
      }
      
      // Set data attribute for CSS hooks
      doc.setAttribute('data-viewport', this.getViewportName());
      doc.setAttribute('data-touch', this.viewportState.isTouch ? 'true' : 'false');
    },

    /**
     * Get human-readable viewport name
     */
    getViewportName: function() {
      if (this.viewportState.is4K) return '4k';
      if (this.viewportState.isLargeDesktop) return 'xl';
      if (this.viewportState.isSmallDesktop) return 'lg';
      if (this.viewportState.isDesktop) return 'md';
      if (this.viewportState.isTablet) return 'sm';
      return 'xs';
    },

    /**
     * Apply responsive adjustments
     */
    applyResponsiveAdjustments: function() {
      // Adjust navbar logo on mobile
      this.adjustNavbarLogo();
      
      // Adjust chart sizes
      this.adjustChartSizes();
      
      // Adjust table display
      this.adjustTableDisplay();
      
      // Handle modals
      this.handleModalResponsiveness();
    },

    /**
     * Adjust navbar logo based on viewport
     */
    adjustNavbarLogo: function() {
      const logo = document.querySelector('.ubc-logo');
      const facilitiesLogo = document.querySelector('.ubc-facilities-logo');
      
      if (logo) {
        if (this.viewportState.isMobile) {
          logo.style.maxHeight = '50px';
        } else if (this.viewportState.isTablet) {
          logo.style.maxHeight = '70px';
        } else {
          logo.style.maxHeight = '85px';
        }
      }
      
      if (facilitiesLogo) {
        if (this.viewportState.isMobile) {
          facilitiesLogo.style.maxHeight = '50px';
        } else if (this.viewportState.isTablet) {
          facilitiesLogo.style.maxHeight = '70px';
        } else {
          facilitiesLogo.style.maxHeight = '85px';
        }
      }
    },

    /**
     * Adjust chart sizes for responsive display
     */
    adjustChartSizes: function() {
      const charts = document.querySelectorAll('.chart-img, .responsive-iframe, .chart-container');
      
      charts.forEach(chart => {
        if (this.viewportState.isMobile) {
          chart.style.maxHeight = '50vh';
        } else if (this.viewportState.isTablet) {
          chart.style.maxHeight = '60vh';
        } else {
          chart.style.maxHeight = '70vh';
        }
      });
    },

    /**
     * Adjust table display for mobile
     */
    adjustTableDisplay: function() {
      const tables = document.querySelectorAll('.asset-table');
      
      tables.forEach(table => {
        const container = table.closest('.table-responsive') || table.closest('.asset-table-container');
        
        if (container && this.viewportState.isMobile) {
          container.style.fontSize = '0.85rem';
        } else if (container) {
          container.style.fontSize = '1rem';
        }
      });
    },

    /**
     * Handle modal responsiveness
     */
    handleModalResponsiveness: function() {
      const modals = document.querySelectorAll('.modal-dialog');
      
      modals.forEach(modal => {
        if (this.viewportState.isMobile) {
          modal.classList.add('modal-dialog-scrollable');
          modal.style.margin = '0.5rem';
        } else {
          modal.classList.remove('modal-dialog-scrollable');
          modal.style.margin = '1.75rem auto';
        }
      });
    },

    /**
     * Subscribe to viewport changes
     */
    subscribe: function(callback) {
      this.listeners.push(callback);
    },

    /**
     * Trigger all listeners
     */
    triggerListeners: function(event, state) {
      this.listeners.forEach(callback => {
        try {
          callback(event, state);
        } catch (e) {
          console.error('Error in responsive listener:', e);
        }
      });
    },

    /**
     * Get current viewport info
     */
    getInfo: function() {
      return {
        ...this.viewportState,
        viewportName: this.getViewportName()
      };
    },

    /**
     * Log current state (for debugging)
     */
    logState: function() {
      console.table(this.viewportState);
    }
  };

  // ============================================
  // 2. TOUCH DEVICE ENHANCEMENTS
  // ============================================

  const TouchManager = {
    init: function() {
      if (ResponsiveManager.viewportState.isTouch) {
        document.documentElement.classList.add('touch-device');
        this.enhanceTouchTargets();
        this.enableTouchScrolling();
      }
    },

    enhanceTouchTargets: function() {
      // Increase button touch targets
      const buttons = document.querySelectorAll('button, a.btn, input[type="button"]');
      buttons.forEach(button => {
        button.style.minHeight = '44px';
        button.style.minWidth = '44px';
      });
    },

    enableTouchScrolling: function() {
      // Enable momentum scrolling on iOS
      const scrollableElements = document.querySelectorAll('.table-responsive, .asset-table-container');
      scrollableElements.forEach(element => {
        element.style.webkitOverflowScrolling = 'touch';
      });
    }
  };

  // ============================================
  // 3. PERFORMANCE MONITORING
  // ============================================

  const PerformanceMonitor = {
    init: function() {
      // Warn if connection is slow and DOM is large
      if (ResponsiveManager.viewportState.connection === '4g' || 
          ResponsiveManager.viewportState.connection === 'lte') {
        console.log('High-speed connection detected');
      } else if (ResponsiveManager.viewportState.connection === '2g' || 
                 ResponsiveManager.viewportState.connection === '3g') {
        console.warn('Slow connection detected. Consider optimizing images and assets.');
      }
      
      // Monitor page visibility to pause animations
      ResponsiveManager.subscribe((event) => {
        if (event === 'hide') {
          this.pauseAnimations();
        } else if (event === 'show') {
          this.resumeAnimations();
        }
      });
    },

    pauseAnimations: function() {
      document.querySelectorAll('[class*="animation"]').forEach(el => {
        el.style.animationPlayState = 'paused';
      });
    },

    resumeAnimations: function() {
      document.querySelectorAll('[class*="animation"]').forEach(el => {
        el.style.animationPlayState = 'running';
      });
    }
  };

  // ============================================
  // 4. IMAGE OPTIMIZATION
  // ============================================

  const ImageOptimizer = {
    init: function() {
      // Use lazy loading for images
      this.setupLazyLoading();
    },

    setupLazyLoading: function() {
      if ('IntersectionObserver' in window && 'loading' in HTMLImageElement.prototype) {
        const images = document.querySelectorAll('img[data-src]');
        images.forEach(img => {
          img.setAttribute('loading', 'lazy');
          if (img.dataset.src) {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
          }
        });
      }
    }
  };

  // ============================================
  // 5. INITIALIZATION
  // ============================================

  document.addEventListener('DOMContentLoaded', function() {
    try {
      // Initialize ResponsiveManager first (other managers depend on it)
      if (ResponsiveManager && typeof ResponsiveManager.init === 'function') {
        ResponsiveManager.init();
      }
      
      // Initialize other managers safely
      if (TouchManager && typeof TouchManager.init === 'function') {
        TouchManager.init();
      }
      
      if (PerformanceMonitor && typeof PerformanceMonitor.init === 'function') {
        PerformanceMonitor.init();
      }
      
      if (ImageOptimizer && typeof ImageOptimizer.init === 'function') {
        ImageOptimizer.init();
      }
      
      console.log('%c✓ Responsive Design System Loaded', 'color: #002145; font-weight: bold; font-size: 14px;');
    } catch (error) {
      console.error('Error initializing Responsive Design System:', error);
    }
  });

  // Expose ResponsiveManager to global scope for external use
  window.ResponsiveManager = ResponsiveManager;

})();

// ============================================
// 6. CHART RESPONSIVENESS HELPER
// ============================================

/**
 * Helper function to make charts responsive
 * Works with Chart.js, ECharts, etc.
 */
window.makeChartsResponsive = function() {
  const charts = document.querySelectorAll('[data-chart-type]');
  
  charts.forEach(chartElement => {
    const type = chartElement.dataset.chartType;
    
    // Adjust based on viewport
    if (ResponsiveManager.viewportState.isMobile) {
      chartElement.dataset.responsive = 'true';
      chartElement.style.maxHeight = '50vh';
    } else if (ResponsiveManager.viewportState.isTablet) {
      chartElement.style.maxHeight = '60vh';
    } else {
      chartElement.style.maxHeight = '80vh';
    }
  });
  
  // Trigger chart resize if using Chart.js
  if (typeof Chart !== 'undefined' && Chart.instances) {
    Chart.instances.forEach(instance => {
      instance.resize();
    });
  }
  
  // Trigger chart resize if using ECharts
  if (typeof echarts !== 'undefined') {
    const charts = echarts.instances || [];
    charts.forEach(chart => {
      chart.resize();
    });
  }
};

// Re-initialize charts on viewport change
window.ResponsiveManager.subscribe(function(event, state) {
  if (event === 'resize' || event === 'orientationchange') {
    window.makeChartsResponsive();
  }
});

// ============================================
// 7. TABLE RESPONSIVENESS HELPER
// ============================================

/**
 * Helper function to make tables card-based on mobile
 */
window.makeTablesResponsive = function() {
  if (ResponsiveManager.viewportState.isMobile) {
    document.querySelectorAll('.responsive-table').forEach(table => {
      if (!table.classList.contains('card-view')) {
        table.classList.add('card-view');
      }
    });
  } else {
    document.querySelectorAll('.responsive-table').forEach(table => {
      table.classList.remove('card-view');
    });
  }
};

// Initialize table responsiveness
window.ResponsiveManager.subscribe(function(event, state) {
  if (event === 'resize') {
    window.makeTablesResponsive();
  }
});

// ============================================
// 8. FORM RESPONSIVENESS
// ============================================

/**
 * Enhance form inputs for mobile
 */
window.enhanceFormResponsiveness = function() {
  const inputs = document.querySelectorAll('input, textarea, select');
  
  inputs.forEach(input => {
    if (ResponsiveManager.viewportState.isTouch) {
      input.style.fontSize = '16px'; // Prevent auto-zoom on iOS
      input.style.minHeight = '44px'; // Touch-friendly sizing
    }
  });
};

document.addEventListener('DOMContentLoaded', function() {
  // Initialize ResponsiveManager
  window.ResponsiveManager.init();
  window.enhanceFormResponsiveness();
});

// Re-enhance on viewport changes
window.ResponsiveManager.subscribe(function(event, state) {
  if (event === 'resize') {
    window.enhanceFormResponsiveness();
  }
});
