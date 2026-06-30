import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorAlert from '../ErrorAlert'

describe('ErrorAlert', () => {
  it('renders nothing when message is empty', () => {
    const { container } = render(<ErrorAlert message="" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders message when provided', () => {
    render(<ErrorAlert message="Something went wrong" />)
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<ErrorAlert message="Error" onClose={onClose} />)
    fireEvent.click(screen.getByLabelText('关闭'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not show close button when onClose is not provided', () => {
    render(<ErrorAlert message="Error" />)
    expect(screen.queryByLabelText('关闭')).not.toBeInTheDocument()
  })
})
