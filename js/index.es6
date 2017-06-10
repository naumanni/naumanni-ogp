/* eslint-disable no-unused-vars */
import {Record} from 'immutable'
import React from 'react'
import {FormattedMessage as _FM} from 'react-intl'


const MAX_DESCRIPTION = 50
const OGPMetaRecord = Record({
  description: null,
  image: null,
  target_url: null,
  title: null,
  type: null,
  url: null,
  content_type: null,
  error: null,
})


export default function initialize({api, uiComponents}) {
  const {IconFont} = uiComponents

  uiComponents.TimelineStatus = class OGPTimelineStatus extends uiComponents.TimelineStatus {
    renderMedia() {
      const {status} = this.props
      const ogp = status.getExtended('ogp')

      if(!ogp)
        return super.renderMedia()

      // TODO: React 17はやくきてくれー
      return (
        <div>
          {super.renderMedia()}

          <div className="ogp-urlMetas" key="ogp">
            {ogp.map((meta) => this.renderURLMeta(meta))}
          </div>
        </div>
      )
    }

    renderURLMeta(meta) {
      meta = new OGPMetaRecord(meta)
      // html以外にはcontent_typeがつく
      if(meta.content_type) {
        return null
      }
      // errorだったら表示しない
      if(meta.error) {
        return null
      }

      let style
      const {image, title, target_url} = meta
      let description = meta.description
      const url = new URL(meta.url)

      if(image) {
        // TODO: imageがクソデカイとどうなるのか?
        style = {
          backgroundImage: `url(${image})`
        }
      }

      if(description && description.length > MAX_DESCRIPTION)
        description = description.substring(0, MAX_DESCRIPTION) + '…'

      // Twitterは画像の大きさで見た目をわけているみたいだけどまぁいいや
      return (
        <a className="ogp-urlMeta" key={target_url} href={target_url} target="_blank">
          {image && <div className="ogp-urlMeta-image" style={style} />}
          <div className="ogp-urlMeta-texts">
            {title && <h1 className="ogp-urlMeta-title">{title}</h1>}
            {description && <p className="ogp-urlMeta-description">{description}</p>}
            <div className="ogp-urlMeta-url">{url.host}</div>
          </div>
        </a>
      )
    }
  }
}
