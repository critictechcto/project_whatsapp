import { describe, expect, it } from 'vitest'
import { buyerMessages, messageStart, messagesShown, sellerMessages, storyBeats, visibleBeats } from './storyScreens'
import { STORY_CHAPTER_COUNT } from './storyChapters'
import { samplePose, tracks } from './webgl/timeline'

describe('story screens', () => {
  it('has beats for every chapter and messages on valid beats', () => {
    expect(storyBeats).toHaveLength(STORY_CHAPTER_COUNT)
    for (const message of [...buyerMessages, ...sellerMessages]) {
      expect(message.beat).toBeLessThan(storyBeats[message.chapter])
      expect(messageStart(message)).toBeGreaterThanOrEqual(message.chapter)
      expect(messageStart(message)).toBeLessThan(message.chapter + 1)
    }
  })

  it('counts the beats showing inside a chapter', () => {
    expect(visibleBeats(0, 3)).toBe(0)
    expect(visibleBeats(0.06, 3)).toBe(1)
    expect(visibleBeats(0.5, 3)).toBe(2)
    expect(visibleBeats(1, 3)).toBe(3)
    expect(visibleBeats(1, 4)).toBe(4)
  })

  it('keeps earlier chapters in the chat history', () => {
    expect(messagesShown(buyerMessages, 0, 0)).toHaveLength(0)
    expect(messagesShown(buyerMessages, 0, 1)).toHaveLength(1)
    const atPayment = messagesShown(buyerMessages, 3, 1)
    expect(atPayment.at(-1)?.lines).toEqual(['How would you like to pay ₹540?'])
    expect(messagesShown(buyerMessages, 4, 4)).toHaveLength(buyerMessages.length)
  })
})

describe('story timeline', () => {
  it('eases between keyframes and holds at the ends', () => {
    const track = tracks.templateCard
    expect(samplePose(track, -1)).toEqual(track[0])
    expect(samplePose(track, 10)).toEqual(track[track.length - 1])
    const mid = samplePose(track, 0.175)
    expect(mid.scale).toBeCloseTo(0.5)
  })

  it('hides props outside their chapters', () => {
    expect(samplePose(tracks.templateCard, 0.5).scale).toBe(1)
    expect(samplePose(tracks.templateCard, 2).scale).toBe(0)
    expect(samplePose(tracks.paymentCard, 1).scale).toBe(0)
    expect(samplePose(tracks.paymentCard, 3.6).scale).toBe(1)
    expect(samplePose(tracks.sellerPhone, 3).scale).toBe(0)
    expect(samplePose(tracks.sellerPhone, 4.6).scale).toBeGreaterThan(0)
    for (const track of tracks.products) expect(samplePose(track, 1.8).scale).toBe(1)
  })
})
