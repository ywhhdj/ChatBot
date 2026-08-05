export class useForceLandscape {
  constructor(breakpoint = 768) {
    this.breakpoint = breakpoint
  }

  breakpoint: number
  private isSmall(){
    return window.innerWidth <= this.breakpoint && window.innerHeight > window.innerWidth
  }

  private applyCssRotate(){
    document.body.classList.add('force-landscape')
  }

  private removeCssRotate(){
    document.body.classList.remove('force-landscape')
  }

  public async tryLock(){
    // 先试原生 API
    if (screen.orientation?.lock) {
      try {
        await screen.orientation.lock('landscape')
        return true
      } catch {
        // fall through
      }
    }
    // 降级 CSS
    this.applyCssRotate()
    return false
  }

  public unlock(){
    screen.orientation?.unlock()
    this.removeCssRotate()
  }

  // 旋转后也要重新判断（比如用户手动横过来再竖回去）
  public onResize = () => {
    if (this.isSmall()) {
      this.applyCssRotate()
    } else {
      this.removeCssRotate()
    }
  }

  public init(){
    if(this.isSmall()){
      this.applyCssRotate()
    }
    window.addEventListener('resize', this.onResize)
    window.addEventListener('orientationchange', this.onResize)
  }
  public destroy(){
    window.removeEventListener('resize', this.onResize)
    window.removeEventListener('orientationchange', this.onResize)
    this.removeCssRotate()
  }
}