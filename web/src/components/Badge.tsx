interface Props {
  kind: string;
  testId?: string;
}

export function Badge({ kind, testId }: Props): JSX.Element {
  return (
    <span className={`badge badge-${kind}`} data-testid={testId}>
      {kind}
    </span>
  );
}
