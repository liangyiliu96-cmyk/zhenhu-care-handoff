import { Box, Skeleton, Typography } from '@mui/material';
import { CircleAlert, Inbox } from 'lucide-react';

interface LoadingSkeletonProps {
  lines?: number;
  height?: number;
}

export function LoadingSkeleton({ lines = 3, height = 24 }: LoadingSkeletonProps) {
  return (
    <Box>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          variant="rectangular"
          height={height}
          sx={{ mb: 1, borderRadius: 1 }}
          animation="pulse"
        />
      ))}
    </Box>
  );
}

export function CardSkeleton({ width = '100%', height = 80 }: { width?: string; height?: number }) {
  return (
    <Skeleton
      variant="rectangular"
      width={width}
      height={height}
      sx={{ borderRadius: 1.5 }}
      animation="pulse"
    />
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Box
      sx={{
        p: 2, bgcolor: 'error.light', borderRadius: 1,
        border: '1px solid', borderColor: 'error.main',
        display: 'flex', alignItems: 'center', gap: 1,
      }}
    >
      <CircleAlert size={18} color="#B63B3B" />
      <Typography variant="body2" sx={{ color: 'error.dark', flex: 1 }}>
        {message}
      </Typography>
      {onRetry && (
        <Box
          component="button"
          onClick={onRetry}
          sx={{
            border: 'none', bg: 'transparent', cursor: 'pointer',
            color: 'error.dark', fontSize: 13, fontWeight: 600,
            textDecoration: 'underline',
          }}
        >
          重试
        </Box>
      )}
    </Box>
  );
}

export function EmptyState({ icon = '📋', title, description }: { icon?: string; title: string; description?: string }) {
  return (
    <Box sx={{ textAlign: 'center', py: 6, px: 2 }}>
      {icon ? <Typography sx={{ fontSize: 28, mb: 1 }}>{icon}</Typography> : <Box sx={{ width: 38, height: 38, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: 'primary.light', color: 'primary.dark', mx: 'auto', mb: 1.25 }}><Inbox size={20} /></Box>}
      <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
      {description && <Typography variant="body2" color="text.secondary" mt={0.6} sx={{ maxWidth: 480, mx: 'auto', lineHeight: 1.65 }}>{description}</Typography>}
    </Box>
  );
}
