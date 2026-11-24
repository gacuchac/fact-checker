interface Props {
  message: string;
  retry: () => void;
}

export function LoadError({ message, retry }: Props): JSX.Element {
  return (
    <p className="issue">
      {message}{" "}
      <button type="button" data-testid="retry-button" onClick={retry}>
        Retry
      </button>
    </p>
  );
}
