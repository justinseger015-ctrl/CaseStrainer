import { createRouter, createWebHistory } from 'vue-router';

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: {
      title: 'CaseStrainer - Legal Citation Validator',
      metaTags: [
        {
          name: 'description',
          content: 'Validate, analyze, and manage legal citations with CaseStrainer. The powerful tool for legal professionals.'
        },
        {
          property: 'og:title',
          content: 'CaseStrainer - Legal Citation Validator'
        },
        {
          property: 'og:description',
          content: 'Validate, analyze, and manage legal citations with CaseStrainer. The powerful tool for legal professionals.'
        },
        {
          property: 'og:type',
          content: 'website'
        }
      ]
    }
  },
  {
    path: '/enhanced-validator',
    name: 'EnhancedValidator',
    component: () => import('@/views/EnhancedValidator.vue'),
    meta: {
      title: 'Enhanced Validator | CaseStrainer',
      metaTags: [
        {
          name: 'description',
          content: 'Use our enhanced validator to check legal citations for accuracy and validity. Supports multiple input methods including file upload and text paste.'
        }
      ]
    }
  },
  // Catch-all route for 404s
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: {
      title: '404 - Page Not Found | CaseStrainer'
    }
  }
];

const router = createRouter({
  history: createWebHistory('/casestrainer/'),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // Return saved position when using back/forward buttons
    if (savedPosition) {
      return savedPosition;
    }
    // Scroll to top when navigating to a new route
    if (to.hash) {
      return {
        el: to.hash,
        behavior: 'smooth',
        top: 100 // Offset for fixed header
      };
    }
    return { top: 0, behavior: 'smooth' };
  }
});

// Update page title and meta tags on route change
router.beforeEach((to, from, next) => {
  // Set the page title
  document.title = to.meta.title || 'CaseStrainer';
  
  // Remove any existing meta tags
  const existingMetaTags = document.querySelectorAll('meta[data-vue-router-controlled]');
  existingMetaTags.forEach(tag => tag.parentNode.removeChild(tag));
  
  // Add new meta tags
  if (to.meta.metaTags) {
    to.meta.metaTags.forEach(tag => {
      const metaTag = document.createElement('meta');
      Object.keys(tag).forEach(key => {
        metaTag.setAttribute(key, tag[key]);
      });
      metaTag.setAttribute('data-vue-router-controlled', '');
      document.head.appendChild(metaTag);
    });
  }
  
  next();
});

export default router;
