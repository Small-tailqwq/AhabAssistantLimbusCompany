using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace AALC.CloneHost
{
    /// <summary>窗口顶部工具栏，尺寸与样式对应 AAALC 的操作栏与 Button.small。</summary>
    internal sealed class HostToolbar : Panel
    {
        private const int LogicalHeight = 48;
        private const int LogicalGutter = 16;
        private const int LogicalSpacing = 8;
        private readonly HostToggleButton _muteButton;
        private readonly HostToggleButton _inputButton;

        internal event EventHandler MuteClicked;
        internal event EventHandler InputClicked;

        internal HostToolbar()
        {
            // 设置尺寸会同步触发 OnLayout，按钮必须先创建。
            _muteButton = new HostToggleButton("关闭声音", "开启声音");
            _inputButton = new HostToggleButton("关闭输入", "开启输入");
            Dock = DockStyle.Top;
            BackColor = HostPalette.SurfaceWindow;
            Height = LogicalToDeviceUnits(LogicalHeight);
            _muteButton.Click += delegate
            {
                EventHandler handler = MuteClicked;
                if (handler != null)
                {
                    handler(this, EventArgs.Empty);
                }
            };
            _inputButton.Click += delegate
            {
                EventHandler handler = InputClicked;
                if (handler != null)
                {
                    handler(this, EventArgs.Empty);
                }
            };
            Controls.Add(_muteButton);
            Controls.Add(_inputButton);
        }

        internal bool Muted
        {
            set { _muteButton.Checked = value; }
        }

        internal bool InputBlocked
        {
            set { _inputButton.Checked = value; }
        }

        /// <summary>阻止输入时把焦点留在工具栏，RDP 控件不再收到键盘。</summary>
        internal void TakeFocus()
        {
            _inputButton.Focus();
        }

        protected override void OnLayout(LayoutEventArgs eventArgs)
        {
            base.OnLayout(eventArgs);
            int right = ClientSize.Width - LogicalToDeviceUnits(LogicalGutter);
            foreach (HostToggleButton button in new[] { _inputButton, _muteButton })
            {
                button.Size = button.PreferredButtonSize();
                button.Location = new Point(
                    right - button.Width,
                    (ClientSize.Height - button.Height) / 2);
                right = button.Left - LogicalToDeviceUnits(LogicalSpacing);
            }
        }

        protected override void OnDpiChangedAfterParent(EventArgs eventArgs)
        {
            base.OnDpiChangedAfterParent(eventArgs);
            Height = LogicalToDeviceUnits(LogicalHeight);
            PerformLayout();
        }

        protected override void OnPaint(PaintEventArgs eventArgs)
        {
            base.OnPaint(eventArgs);
            using (Pen pen = new Pen(HostPalette.BorderSubtle))
            {
                eventArgs.Graphics.DrawLine(pen, 0, Height - 1, Width, Height - 1);
            }
        }
    }

    /// <summary>
    /// 自绘的开关按钮。悬停与按下用叠加层（6% / 12%）表现，键盘焦点显示主色外框；
    /// 开启状态同时换文字，不只靠颜色区分。
    /// </summary>
    internal sealed class HostToggleButton : Control
    {
        private const int LogicalButtonHeight = 30;
        private const int LogicalMinWidth = 92;
        private const int LogicalPadding = 12;
        private const int LogicalRadius = 6;
        private const int HoverOverlayAlpha = 15;
        private const int PressedOverlayAlpha = 31;
        private readonly string _offText;
        private readonly string _onText;
        private bool _checked;
        private bool _hovered;
        private bool _pressed;

        internal HostToggleButton(string offText, string onText)
        {
            _offText = offText;
            _onText = onText;
            SetStyle(
                ControlStyles.AllPaintingInWmPaint
                | ControlStyles.OptimizedDoubleBuffer
                | ControlStyles.ResizeRedraw
                | ControlStyles.UserPaint
                | ControlStyles.Selectable,
                true);
            BackColor = HostPalette.SurfaceWindow;
            ForeColor = HostPalette.TextPrimary;
            Font = HostPalette.BodyFont;
            Cursor = Cursors.Hand;
            TabStop = true;
            AccessibleRole = AccessibleRole.CheckButton;
            UpdateText();
        }

        internal bool Checked
        {
            get { return _checked; }
            set
            {
                if (_checked == value)
                {
                    return;
                }
                _checked = value;
                UpdateText();
                Invalidate();
            }
        }

        internal Size PreferredButtonSize()
        {
            int textWidth = Math.Max(
                TextRenderer.MeasureText(_offText, Font).Width,
                TextRenderer.MeasureText(_onText, Font).Width);
            return new Size(
                Math.Max(
                    LogicalToDeviceUnits(LogicalMinWidth),
                    textWidth + 2 * LogicalToDeviceUnits(LogicalPadding)),
                LogicalToDeviceUnits(LogicalButtonHeight));
        }

        private void UpdateText()
        {
            Text = _checked ? _onText : _offText;
            AccessibleName = Text;
        }

        protected override void OnMouseEnter(EventArgs eventArgs)
        {
            base.OnMouseEnter(eventArgs);
            _hovered = true;
            Invalidate();
        }

        protected override void OnMouseLeave(EventArgs eventArgs)
        {
            base.OnMouseLeave(eventArgs);
            _hovered = false;
            Invalidate();
        }

        protected override void OnMouseDown(MouseEventArgs eventArgs)
        {
            base.OnMouseDown(eventArgs);
            if (eventArgs.Button == MouseButtons.Left)
            {
                _pressed = true;
                Invalidate();
            }
        }

        protected override void OnMouseUp(MouseEventArgs eventArgs)
        {
            base.OnMouseUp(eventArgs);
            _pressed = false;
            Invalidate();
        }

        protected override void OnKeyDown(KeyEventArgs eventArgs)
        {
            base.OnKeyDown(eventArgs);
            if (eventArgs.KeyCode == Keys.Space || eventArgs.KeyCode == Keys.Enter)
            {
                OnClick(EventArgs.Empty);
                eventArgs.Handled = true;
            }
        }

        protected override void OnGotFocus(EventArgs eventArgs)
        {
            base.OnGotFocus(eventArgs);
            Invalidate();
        }

        protected override void OnLostFocus(EventArgs eventArgs)
        {
            base.OnLostFocus(eventArgs);
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs eventArgs)
        {
            Graphics graphics = eventArgs.Graphics;
            graphics.SmoothingMode = SmoothingMode.AntiAlias;
            graphics.Clear(BackColor);
            Rectangle bounds = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = RoundedRectangle(bounds, LogicalToDeviceUnits(LogicalRadius)))
            {
                Color fill = _checked ? HostPalette.AccentSubtle : HostPalette.SurfaceCard;
                using (SolidBrush brush = new SolidBrush(fill))
                {
                    graphics.FillPath(brush, path);
                }
                if (_pressed || _hovered)
                {
                    int alpha = _pressed ? PressedOverlayAlpha : HoverOverlayAlpha;
                    using (SolidBrush overlay = new SolidBrush(Color.FromArgb(alpha, Color.White)))
                    {
                        graphics.FillPath(overlay, path);
                    }
                }
                Color border = Focused || _checked
                    ? HostPalette.Accent
                    : HostPalette.BorderDefault;
                using (Pen pen = new Pen(border))
                {
                    graphics.DrawPath(pen, path);
                }
            }
            TextRenderer.DrawText(
                graphics,
                Text,
                Font,
                ClientRectangle,
                _checked ? HostPalette.Accent : ForeColor,
                TextFormatFlags.HorizontalCenter
                | TextFormatFlags.VerticalCenter
                | TextFormatFlags.SingleLine);
        }

        private static GraphicsPath RoundedRectangle(Rectangle bounds, int radius)
        {
            int diameter = radius * 2;
            GraphicsPath path = new GraphicsPath();
            path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
            path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
            path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
            path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
            path.CloseFigure();
            return path;
        }
    }
}
